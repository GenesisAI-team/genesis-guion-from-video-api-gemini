"""Recorrido local completo: vídeo → guion → exportación, sin API real (GEN-50).

Aceptación de la Fase 4: el flujo entero corre con dobles locales (sin red,
sin clave y sin cargos), los errores y la cancelación quedan cubiertos y los
exportados verifican la fuente real y los tiempos medidos.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Sequence
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from genesis_video_ai.analysis.ffprobe import probe_video
from genesis_video_ai.gemini.port import ScriptEntry, ScriptProposal, ScriptProposalRequest
from genesis_video_ai.jobs.export import export_proposal_json, export_proposal_markdown
from genesis_video_ai.jobs.flow import ScriptJobController
from genesis_video_ai.models.contracts import Segment, SourceMedia

PAYLOAD: dict[str, object] = {
    "streams": [
        {"index": 0, "codec_type": "video", "codec_name": "h264", "width": 1280, "height": 720},
        {"index": 1, "codec_type": "audio", "codec_name": "aac"},
    ],
    "format": {"duration": "120.0", "format_name": "mov,mp4,m4a,3gp,3g2,mj2"},
}


def runner_sintetico(args: Sequence[str]) -> CompletedProcess[str]:
    """Runner inyectado: sustituye al ffprobe real sin binarios ni red."""
    return CompletedProcess(
        args=list(args),
        returncode=0,
        stdout=json.dumps(PAYLOAD),
        stderr="",
    )


def test_recorrido_local_completo_con_fakes(tmp_path: Path) -> None:
    original = tmp_path / "original.mp4"
    original.write_bytes(b"x")
    sesion = tmp_path / "sesion"
    sesion.mkdir()
    puerto = _PuertoEcoScript()
    controlador = ScriptJobController(
        puerto,
        probe_runner=runner_sintetico,
        temp_root=sesion,
    )

    analisis = controlador.analyze(original)
    assert analisis.outcome == "done"
    fuente = analisis.source
    assert fuente is not None

    seleccion = (
        Segment(source_id=fuente.id, start_s=0.0, end_s=45.0),
        Segment(source_id=fuente.id, start_s=60.0, end_s=105.0),
    )
    generacion = controlador.generate(fuente, seleccion, 90.0)
    assert generacion.outcome == "done"
    propuesta = generacion.proposal
    assert propuesta is not None
    assert propuesta.total_duration_s == pytest.approx(90.0)
    assert len(puerto.requests) == 1
    assert puerto.requests[0].segments == seleccion

    ruta_json = export_proposal_json(propuesta, fuente, tmp_path / "salidas" / "guion.json")
    ruta_md = export_proposal_markdown(propuesta, fuente, tmp_path / "salidas" / "guion.md")

    payload = json.loads(ruta_json.read_text(encoding="utf-8"))
    assert payload["source"]["path"] == str(original.resolve())
    assert payload["source"]["duration_s"] == pytest.approx(120.0)
    assert payload["total_duration_s"] == pytest.approx(90.0)
    assert payload["entries"][0]["start_s"] == pytest.approx(0.0)
    assert payload["entries"][1]["end_s"] == pytest.approx(105.0)
    texto_md = ruta_md.read_text(encoding="utf-8")
    assert f"`{original.resolve()}`" in texto_md
    assert "Duración total calculada: 90 s" in texto_md
    assert "| 2 | 60 | 105 | 45 |" in texto_md

    assert list(sesion.iterdir()) == []


def test_recorrido_local_cancelado_limpia_los_temporales(tmp_path: Path) -> None:
    original = tmp_path / "original.mp4"
    original.write_bytes(b"x")
    sesion = tmp_path / "sesion"
    sesion.mkdir()
    evento = threading.Event()
    evento.set()
    fuente = _fuente_de_analisis(original)
    controlador = ScriptJobController(
        _PuertoEcoScript(),
        probe_runner=runner_sintetico,
        cancel_event=evento,
        temp_root=sesion,
    )

    generacion = controlador.generate(
        fuente,
        (Segment(source_id=fuente.id, start_s=0.0, end_s=90.0),),
        90.0,
    )
    assert generacion.outcome == "cancelled"

    assert list(sesion.iterdir()) == []


def test_recorrido_local_con_ffprobe_real(mp4_con_audio: Path, tmp_path: Path) -> None:
    """Con ffprobe del sistema: el análisis mide el MP4 sintético de verdad."""
    puerto = _PuertoEcoScript()
    controlador = ScriptJobController(puerto)

    analisis = controlador.analyze(mp4_con_audio)
    assert analisis.outcome == "done"
    fuente = analisis.source
    assert fuente is not None
    assert fuente.container == "mp4"
    assert 0 < fuente.duration_s < 1.5

    seleccion = (
        Segment(
            source_id=fuente.id,
            start_s=0.0,
            end_s=max(fuente.duration_s, 0.1),
        ),
    )
    generacion = controlador.generate(fuente, seleccion, fuente.duration_s)
    assert generacion.outcome == "done"
    propuesta = generacion.proposal
    assert propuesta is not None
    assert propuesta.total_duration_s == pytest.approx(fuente.duration_s, rel=1e-3)

    ruta_json = export_proposal_json(propuesta, fuente, tmp_path / "salidas" / "guion.json")
    payload = json.loads(ruta_json.read_text(encoding="utf-8"))
    assert payload["source"]["path"] == str(mp4_con_audio.resolve())
    assert payload["entries"][0]["end_s"] <= fuente.duration_s + 1e-3


def _fuente_de_analisis(original: Path) -> SourceMedia:
    return probe_video(original, runner=runner_sintetico)


class _PuertoEcoScript:
    """Doble del puerto: el guion deriva del material medido, sin inferencia."""

    def __init__(self) -> None:
        self.requests: list[ScriptProposalRequest] = []

    def propose_script(self, request: ScriptProposalRequest) -> ScriptProposal:
        self.requests.append(request)
        return ScriptProposal(
            source_id=request.source.id,
            requested_duration_s=request.requested_duration_s,
            entries=tuple(
                ScriptEntry(
                    source_id=segmento.source_id,
                    start_s=segmento.start_s,
                    end_s=segmento.end_s,
                    narration=f"Narración sobre [{segmento.start_s:g}, {segmento.end_s:g}] s.",
                    justification="Derivado del material medido",
                )
                for segmento in request.segments
            ),
        )
