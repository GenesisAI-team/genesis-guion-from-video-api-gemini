"""Controlador de trabajos: estados, cancelación, errores, límites y temporales (GEN-50)."""

from __future__ import annotations

import json
import threading
from collections.abc import Sequence
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any

import pytest

from genesis_video_ai.analysis.ffprobe import (
    AnalysisError,
    FileSizeLimitExceededError,
    SourceNotFoundError,
    UnsupportedContainerError,
)
from genesis_video_ai.editorial.sequence import (
    ExcessMaterialError,
    InsufficientMaterialError,
)
from genesis_video_ai.gemini.errors import GeminiQuotaExceededError
from genesis_video_ai.gemini.port import (
    ScriptedGeminiScriptPort,
    ScriptEntry,
    ScriptProposal,
    ScriptProposalRequest,
)
from genesis_video_ai.jobs.flow import JobEvent, JobResult, ScriptJobController
from genesis_video_ai.jobs.tempfiles import SESSION_TEMP_PREFIX
from genesis_video_ai.models.contracts import Segment, SourceMedia

PROBE_PAYLOAD: dict[str, Any] = {
    "streams": [{"index": 0, "codec_type": "video", "codec_name": "h264"}],
    "format": {"duration": "120.0", "format_name": "mov,mp4,m4a,3gp,3g2,mj2"},
}


def runner_de_prueba(args: Sequence[str]) -> CompletedProcess[str]:
    return CompletedProcess(
        args=list(args),
        returncode=0,
        stdout=json.dumps(PROBE_PAYLOAD),
        stderr="",
    )


def controlador(
    respuestas: Sequence[ScriptProposal | Exception] = (),
    **ajustes: Any,
) -> tuple[ScriptJobController, ScriptedGeminiScriptPort]:
    """Controlador con el puerto Gemini sustituido por un doble programado."""
    puerto = ScriptedGeminiScriptPort(responses=list(respuestas))
    return ScriptJobController(puerto, probe_runner=runner_de_prueba, **ajustes), puerto


def fuente() -> SourceMedia:
    return SourceMedia(
        id="src-1",
        path=Path("C:/medias/original.mp4").resolve(),
        container="mp4",
        duration_s=120.0,
        size_bytes=4242,
        format_name="mov,mp4,m4a,3gp,3g2,mj2",
    )


def segmento(start_s: float, end_s: float) -> Segment:
    return Segment(source_id="src-1", start_s=start_s, end_s=end_s)


def propuesta() -> ScriptProposal:
    return ScriptProposal(
        source_id="src-1",
        requested_duration_s=90.0,
        entries=(
            ScriptEntry(
                source_id="src-1",
                start_s=0.0,
                end_s=90.0,
                narration="Guion real.",
                justification="Bloque medido",
            ),
        ),
    )


class TestAnalizar:
    def test_mide_el_original_y_termina_en_done(self, tmp_path: Path) -> None:
        original = tmp_path / "original.mp4"
        original.write_bytes(b"x")
        controlador_local, _ = controlador()

        resultado = controlador_local.analyze(original)

        assert resultado.outcome == "done"
        assert resultado.source is not None
        assert resultado.source.duration_s == pytest.approx(120.0)
        assert resultado.source.container == "mp4"
        assert resultado.proposal is None
        fases = [evento.phase for evento in resultado.events]
        assert fases == ["analyzing", "done"]

    def test_publica_los_eventos_por_el_observador(self, tmp_path: Path) -> None:
        original = tmp_path / "original.mp4"
        original.write_bytes(b"x")
        observados: list[JobEvent] = []
        controlador_local, _ = controlador(on_event=observados.append)

        resultado = controlador_local.analyze(original)

        assert observados == list(resultado.events)

    def test_original_inexistente_falla_tipado(self, tmp_path: Path) -> None:
        controlador_local, _ = controlador()

        resultado = controlador_local.analyze(tmp_path / "ausente.mp4")

        assert resultado.outcome == "failed"
        assert isinstance(resultado.error, SourceNotFoundError)
        assert isinstance(resultado.error, AnalysisError)
        assert [evento.phase for evento in resultado.events] == ["analyzing", "failed"]
        assert resultado.source is None

    def test_contenedor_no_soportado_falla(self, tmp_path: Path) -> None:
        original = tmp_path / "original.avi"
        original.write_bytes(b"x")
        controlador_local, _ = controlador()

        resultado = controlador_local.analyze(original)

        assert resultado.outcome == "failed"
        assert isinstance(resultado.error, UnsupportedContainerError)

    def test_limite_de_peso_rechaza_el_original(self, tmp_path: Path) -> None:
        original = tmp_path / "original.mp4"
        original.write_bytes(b"xx")
        controlador_local, _ = controlador(max_file_bytes=1)

        resultado = controlador_local.analyze(original)

        assert resultado.outcome == "failed"
        assert isinstance(resultado.error, FileSizeLimitExceededError)

    def test_cancelado_durante_el_probing_no_publica_exito(self, tmp_path: Path) -> None:
        """La cancelación que ocurre mientras corre ffprobe gana al resultado."""
        original = tmp_path / "original.mp4"
        original.write_bytes(b"x")
        evento = threading.Event()

        def runner_que_cancela(args: Sequence[str]) -> CompletedProcess[str]:
            evento.set()
            return runner_de_prueba(args)

        controlador_local = ScriptJobController(
            ScriptedGeminiScriptPort(responses=[]),
            probe_runner=runner_que_cancela,
            cancel_event=evento,
        )

        resultado = controlador_local.analyze(original)

        assert resultado.outcome == "cancelled"
        assert resultado.source is None
        assert [evento_fase.phase for evento_fase in resultado.events] == [
            "analyzing",
            "cancelled",
        ]


class TestGenerar:
    def test_valida_solicita_y_entrega_el_guion(self) -> None:
        controlador_local, puerto = controlador(respuestas=[propuesta()])

        resultado = controlador_local.generate(
            fuente(),
            (segmento(60.0, 105.0), segmento(0.0, 45.0)),
            90.0,
        )

        assert resultado.outcome == "done"
        assert resultado.proposal is not None
        assert resultado.proposal.total_duration_s == pytest.approx(90.0)
        assert resultado.source is None
        fases = [evento.phase for evento in resultado.events]
        assert fases == ["validating", "generating", "done"]
        assert len(puerto.requests) == 1
        peticion = puerto.requests[0]
        assert isinstance(peticion, ScriptProposalRequest)
        assert peticion.source.id == "src-1"
        assert [segmento_.start_s for segmento_ in peticion.segments] == [0.0, 60.0]

    def test_material_insuficiente_falla_y_no_llama_al_puerto(self) -> None:
        controlador_local, puerto = controlador()

        resultado = controlador_local.generate(
            fuente(),
            (segmento(0.0, 45.0),),
            90.0,
        )

        assert resultado.outcome == "failed"
        assert isinstance(resultado.error, InsufficientMaterialError)
        assert puerto.requests == []
        assert [evento.phase for evento in resultado.events] == ["validating", "failed"]

    def test_material_excesivo_falla(self) -> None:
        controlador_local, _ = controlador()

        resultado = controlador_local.generate(
            fuente(),
            (segmento(0.0, 100.0),),
            90.0,
        )

        assert resultado.outcome == "failed"
        assert isinstance(resultado.error, ExcessMaterialError)

    def test_tolerancia_absorbe_redondeos_pequenos(self) -> None:
        controlador_local, puerto = controlador(respuestas=[propuesta()])

        resultado = controlador_local.generate(
            fuente(),
            (segmento(0.0, 89.98),),
            90.0,
        )

        assert resultado.outcome == "done"
        assert len(puerto.requests) == 1

    def test_sin_segmentos_falla_por_insuficiencia(self) -> None:
        controlador_local, _ = controlador()

        resultado = controlador_local.generate(fuente(), (), 90.0)

        assert resultado.outcome == "failed"
        assert isinstance(resultado.error, InsufficientMaterialError)

    def test_error_de_cuota_falla_tipado(self) -> None:
        controlador_local, _ = controlador(
            respuestas=[GeminiQuotaExceededError("429: cuota agotada")],
        )

        resultado = controlador_local.generate(fuente(), (segmento(0.0, 90.0),), 90.0)

        assert resultado.outcome == "failed"
        assert isinstance(resultado.error, GeminiQuotaExceededError)

    def test_cancelacion_antes_de_empezar(self) -> None:
        evento = threading.Event()
        evento.set()
        controlador_local, puerto = controlador(respuestas=[propuesta()], cancel_event=evento)

        resultado = controlador_local.generate(fuente(), (segmento(0.0, 90.0),), 90.0)

        assert resultado.outcome == "cancelled"
        assert resultado.proposal is None
        assert puerto.requests == []
        assert [evento_fase.phase for evento_fase in resultado.events] == ["cancelled"]

    def test_la_cancelacion_gana_al_resultado(self) -> None:
        evento = threading.Event()

        class PuertoQueCancela:
            """Doble: cancela durante la generación y aun así devuelve algo."""

            def __init__(self) -> None:
                self.requests: list[ScriptProposalRequest] = []

            def propose_script(self, request: ScriptProposalRequest) -> ScriptProposal:
                self.requests.append(request)
                evento.set()
                return propuesta()

        controlador_local = ScriptJobController(
            PuertoQueCancela(),
            probe_runner=runner_de_prueba,
            cancel_event=evento,
        )

        resultado = controlador_local.generate(fuente(), (segmento(0.0, 90.0),), 90.0)

        assert resultado.outcome == "cancelled"
        assert resultado.proposal is None
        assert [evento_fase.phase for evento_fase in resultado.events] == [
            "validating",
            "generating",
            "cancelled",
        ]

    def test_cancel_pide_la_parada_de_la_operacion_siguiente(self) -> None:
        controlador_local, puerto = controlador(respuestas=[propuesta()])

        controlador_local.cancel()
        resultado = controlador_local.generate(fuente(), (segmento(0.0, 90.0),), 90.0)

        assert resultado.outcome == "cancelled"
        assert puerto.requests == []


class TestTemporales:
    def test_el_temporal_de_sesion_se_elimina_al_terminar(self, tmp_path: Path) -> None:
        original = tmp_path / "original.mp4"
        original.write_bytes(b"x")
        sesion = tmp_path / "sesion"
        sesion.mkdir()
        controlador_local, _ = controlador(temp_root=sesion)

        controlador_local.analyze(original)

        assert list(sesion.iterdir()) == []

    def test_el_temporal_se_elimina_aun_fallando(self, tmp_path: Path) -> None:
        sesion = tmp_path / "sesion"
        sesion.mkdir()
        controlador_local, _ = controlador(temp_root=sesion)

        resultado = controlador_local.analyze(tmp_path / "ausente.mp4")

        assert resultado.outcome == "failed"
        assert list(sesion.iterdir()) == []

    def test_el_temporal_se_elimina_tras_cancelar(self, tmp_path: Path) -> None:
        evento = threading.Event()
        evento.set()
        sesion = tmp_path / "sesion"
        sesion.mkdir()
        controlador_local, _ = controlador(
            respuestas=[propuesta()],
            cancel_event=evento,
            temp_root=sesion,
        )

        controlador_local.generate(fuente(), (segmento(0.0, 90.0),), 90.0)

        assert list(sesion.iterdir()) == []

    def test_el_temporal_existe_durante_y_desaparece_despues(self, tmp_path: Path) -> None:
        original = tmp_path / "original.mp4"
        original.write_bytes(b"x")
        sesion = tmp_path / "sesion"
        sesion.mkdir()
        durante: list[list[str]] = []

        def observador(evento: JobEvent) -> None:
            durante.append([ruta.name for ruta in sesion.iterdir()])

        controlador_local = ScriptJobController(
            ScriptedGeminiScriptPort(responses=[]),
            probe_runner=runner_de_prueba,
            temp_root=sesion,
            on_event=observador,
        )

        resultado = controlador_local.analyze(original)

        assert resultado.outcome == "done"
        nombres = durante[-1]
        assert any(nombre.startswith(SESSION_TEMP_PREFIX) for nombre in nombres)
        assert list(sesion.iterdir()) == []


def test_jobresult_y_jobevent_son_inmutables() -> None:
    evento = JobEvent(phase="done", message="ok")
    resultado = JobResult(outcome="done", events=(evento,))

    with pytest.raises(AttributeError):
        evento.phase = "failed"  # type: ignore[misc]
    with pytest.raises(AttributeError):
        resultado.outcome = "failed"  # type: ignore[misc]
