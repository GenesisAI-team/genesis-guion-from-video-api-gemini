"""Tests del puerto Gemini y su fake (GEN-36 §2)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from genesis_video_ai.gemini.port import (
    FakeGeminiScriptPort,
    GeminiNotAvailableError,
    GeminiScriptPort,
    ScriptProposal,
    ScriptProposalRequest,
)
from genesis_video_ai.models.contracts import Segment, SourceMedia


def make_source(duration_s: float = 42.5) -> SourceMedia:
    """Factoría de la fuente original que se enviaría al puerto."""
    return SourceMedia(
        id="src-1",
        path=Path("C:/medias/original.mp4"),
        container="mp4",
        duration_s=duration_s,
        size_bytes=4242,
        format_name="mov,mp4,m4a,3gp,3g2,mj2",
    )


def make_segment(start_s: float = 0.0, end_s: float = 10.0) -> Segment:
    """Factoría de un segmento del original."""
    return Segment(source_id="src-1", start_s=start_s, end_s=end_s)


def make_request(requested: float = 10.0) -> ScriptProposalRequest:
    """Petición de ejemplo para el puerto."""
    return ScriptProposalRequest(
        source=make_source(),
        segments=(make_segment(),),
        requested_duration_s=requested,
    )


# --- petición ---------------------------------------------------------------


def test_peticion_valida_conoce_selccion_y_duracion() -> None:
    request = make_request(requested=8.5)

    assert request.requested_duration_s == pytest.approx(8.5)
    assert len(request.segments) == 1
    assert request.source.id == "src-1"


def test_peticion_sin_segmentos_es_posible() -> None:
    request = ScriptProposalRequest(source=make_source(), requested_duration_s=10.0)

    assert request.segments == ()


def test_peticion_rechaza_duracion_pedida_invalida() -> None:
    with pytest.raises(ValidationError, match="requested_duration_s"):
        make_request(requested=0.0)


def test_peticion_requiere_fuente() -> None:
    with pytest.raises(ValidationError):
        ScriptProposalRequest(segments=(), requested_duration_s=10.0)  # type: ignore[call-arg]


def test_peticion_rechaza_duracion_no_finita() -> None:
    import math

    with pytest.raises(ValidationError):
        make_request(requested=math.inf)


def test_peticion_no_acepta_campos_extra() -> None:
    with pytest.raises(ValidationError):
        ScriptProposalRequest(  # type: ignore[call-arg]
            source=make_source(),
            requested_duration_s=10.0,
            modelo="gemini-2.5-flash",
        )


# --- puerto -------------------------------------------------------------------


def test_fake_cumple_el_puerto() -> None:
    fake = FakeGeminiScriptPort()

    assert isinstance(fake, GeminiScriptPort)


def test_fake_registra_la_peticion_sin_simular_inferencia() -> None:
    fake = FakeGeminiScriptPort()
    request = make_request()

    with pytest.raises(GeminiNotAvailableError, match="inferencia"):
        fake.propose_script(request)

    assert fake.requests == [request]


def test_fake_acumula_peticiones() -> None:
    fake = FakeGeminiScriptPort()
    first = make_request(requested=5.0)
    second = make_request(requested=6.0)

    for request in (first, second):
        with pytest.raises(GeminiNotAvailableError):
            fake.propose_script(request)

    assert fake.requests == [first, second]


def test_google_no_disponible_es_runtime_error() -> None:
    assert issubclass(GeminiNotAvailableError, RuntimeError)


def test_propuesta_definida_en_gen45_rechaza_campos_extra() -> None:
    """GEN-45 define la forma de la propuesta; sigue siendo sellada."""
    from helpers import make_proposal

    proposal = make_proposal()

    with pytest.raises(ValidationError):
        ScriptProposal(estimado=1)  # type: ignore[call-arg]
    assert proposal.total_duration_s > 0
