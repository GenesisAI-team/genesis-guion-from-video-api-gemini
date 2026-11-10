"""Flujo completo medido -> guion trazable con el cliente Gemini (GEN-45).

Sin red, sin API real y sin binarios externos: el runner de ffprobe y la
sesión de Gemini se inyectan. Verifica que la propuesta final queda trazada
al original y que sin credenciales el fallo es controlado.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Sequence
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any

import pytest

from genesis_video_ai.analysis.ffprobe import probe_video
from genesis_video_ai.editorial.sequence import validate_segment_sequence
from genesis_video_ai.gemini.client import RealGeminiScriptPort
from genesis_video_ai.gemini.config import GeminiClientConfig
from genesis_video_ai.gemini.port import (
    GeminiNotAvailableError,
    ScriptedGeminiScriptPort,
    ScriptEntry,
    ScriptProposal,
    ScriptProposalRequest,
)
from genesis_video_ai.models.contracts import Segment, SourceMedia

PAYLOAD: dict[str, object] = {
    "streams": [
        {
            "index": 0,
            "codec_type": "video",
            "codec_name": "h264",
            "width": 1280,
            "height": 720,
            "avg_frame_rate": "25/1",
        },
        {"index": 1, "codec_type": "audio", "codec_name": "aac"},
    ],
    "format": {
        "duration": "120.0",
        "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
        "tags": {"major_brand": "isom"},
    },
}


def runner_de_prueba(args: Sequence[str]) -> CompletedProcess[str]:
    return CompletedProcess(args=list(args), returncode=0, stdout=json.dumps(PAYLOAD), stderr="")


def fuente_analizada(tmp_path: Path) -> SourceMedia:
    media = tmp_path / "original.mp4"
    media.write_bytes(b"x")
    return probe_video(media, runner=runner_de_prueba)


def peticion_validada(source: SourceMedia) -> ScriptProposalRequest:
    selection = (
        Segment(source_id=source.id, start_s=0.0, end_s=45.0),
        Segment(source_id=source.id, start_s=60.0, end_s=105.0),
    )
    validated = validate_segment_sequence(
        selection,
        source=source,
        requested_duration_s=90.0,
    )
    return ScriptProposalRequest(
        source=source,
        segments=validated.ordered,
        requested_duration_s=90.0,
    )


def test_del_medido_al_guion_trazable_con_doble_programado(tmp_path: Path) -> None:
    source = fuente_analizada(tmp_path)
    request = peticion_validada(source)
    proposal = ScriptProposal(
        source_id=source.id,
        requested_duration_s=90.0,
        entries=(
            ScriptEntry(
                source_id=source.id,
                start_s=0.0,
                end_s=45.0,
                narration="Apertura con material real.",
                justification="Primer bloque medido",
            ),
            ScriptEntry(
                source_id=source.id,
                start_s=60.0,
                end_s=105.0,
                narration="Cierre con material real.",
                justification="Segundo bloque medido",
            ),
        ),
    )
    port = ScriptedGeminiScriptPort(responses=[proposal])

    result = port.propose_script(request)

    assert result.total_duration_s == pytest.approx(90.0)
    assert all(entry.source_id == source.id for entry in result.entries)
    for entry in result.entries:
        assert any(
            measured.start_s <= entry.start_s and entry.end_s <= measured.end_s
            for measured in request.segments
        )
    assert port.requests == [request]


def test_cliente_real_sin_credenciales_falla_de_forma_controlada(tmp_path: Path) -> None:
    source = fuente_analizada(tmp_path)
    request = peticion_validada(source)
    port = RealGeminiScriptPort(GeminiClientConfig(api_key=None))

    with pytest.raises(GeminiNotAvailableError, match="credencial"):
        port.propose_script(request)


def test_flujo_completo_con_sesion_inyectada(tmp_path: Path) -> None:
    source = fuente_analizada(tmp_path)
    request = peticion_validada(source)
    model_json = (
        '{"entries": ['
        '{"start_s": 0.0, "end_s": 45.0, "narration": "Apertura real",'
        ' "justification": "Bloque uno"},'
        '{"start_s": 60.0, "end_s": 105.0, "narration": "Cierre real",'
        ' "justification": "Bloque dos"}'
        "]}"
    )
    calls: list[tuple[str, Any]] = []

    class SesionFalsa:
        """Sesión inyectada: devuelve el JSON programado y registra llamadas."""

        def generate(self, prompt: str, response_schema: Any) -> str:
            calls.append((prompt, response_schema))
            return model_json

    port = RealGeminiScriptPort(
        GeminiClientConfig(api_key="clave-falsa", tolerance_s=0.0),
        session_factory=lambda config: SesionFalsa(),  # type: ignore[arg-type,return-value]
        cancel_event=threading.Event(),
    )

    result = port.propose_script(request)

    assert result.total_duration_s == pytest.approx(90.0)
    assert [entry.start_s for entry in result.entries] == [0.0, 60.0]
    assert all(entry.source_id == source.id for entry in result.entries)
    prompt, schema = calls[0]
    assert source.id in prompt
    assert "[0.0, 45.0]" in prompt
    assert "[60.0, 105.0]" in prompt
    assert schema.__name__ == "ScriptPayload"
