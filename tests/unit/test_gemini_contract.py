"""Tests del contrato de guion trazable y los dobles del puerto (GEN-45)."""

from __future__ import annotations

import math

import pytest
from helpers import make_entry, make_proposal, make_request
from pydantic import ValidationError

from genesis_video_ai.gemini.port import (
    FakeGeminiScriptPort,
    GeminiNotAvailableError,
    GeminiScriptPort,
    ScriptedGeminiScriptPort,
    ScriptEntry,
    ScriptProposal,
)

# --- entrada de guion ---------------------------------------------------------


def test_entrada_valida_expone_duracion_real() -> None:
    entry = make_entry(start_s=2.0, end_s=5.5)

    assert entry.source_id == "src-1"
    assert entry.duration_s == pytest.approx(3.5)
    assert entry.narration
    assert entry.justification == ""


def test_entrada_requiere_narracion() -> None:
    with pytest.raises(ValidationError, match="narration"):
        make_entry(narration="   ")


def test_entrada_rechaza_tiempo_incoherente() -> None:
    with pytest.raises(ValidationError):
        make_entry(start_s=5.0, end_s=5.0)


def test_entrada_rechaza_tiempos_no_finitos() -> None:
    with pytest.raises(ValidationError):
        make_entry(start_s=0.0, end_s=math.inf)


def test_entrada_no_acepta_campos_extra() -> None:
    with pytest.raises(ValidationError):
        ScriptEntry(  # type: ignore[call-arg]
            source_id="src-1",
            start_s=0.0,
            end_s=1.0,
            narration="texto",
            inventado=True,
        )


# --- propuesta ----------------------------------------------------------------


def test_propuesta_trazable_expone_total_calculado() -> None:
    proposal = make_proposal()

    assert proposal.source_id == "src-1"
    assert proposal.requested_duration_s == pytest.approx(8.5)
    assert proposal.total_duration_s == pytest.approx(8.5)
    assert len(proposal.entries) == 1


def test_propuesta_total_suma_las_entradas() -> None:
    entries = (
        make_entry(start_s=0.0, end_s=4.0),
        make_entry(start_s=4.0, end_s=5.5),
    )
    proposal = ScriptProposal(
        source_id="src-1",
        requested_duration_s=5.5,
        entries=entries,
    )

    assert proposal.total_duration_s == pytest.approx(5.5)


def test_propuesta_vacia_no_es_un_guion() -> None:
    with pytest.raises(ValidationError):
        ScriptProposal(source_id="src-1", requested_duration_s=5.0, entries=())


def test_propuesta_exige_coherencia_de_origen() -> None:
    alien = ScriptEntry(
        source_id="src-otra",
        start_s=0.0,
        end_s=4.0,
        narration="texto",
    )

    with pytest.raises(ValidationError, match="src-1"):
        ScriptProposal(
            source_id="src-1",
            requested_duration_s=4.0,
            entries=(alien,),
        )


def test_propuesta_es_inmutable() -> None:
    proposal = make_proposal()

    with pytest.raises(ValidationError):
        proposal.source_id = "otro"


# --- doble programado ---------------------------------------------------------


def test_doble_programado_cumple_el_puerto() -> None:
    double = ScriptedGeminiScriptPort(responses=[make_proposal()])

    assert isinstance(double, GeminiScriptPort)


def test_doble_programado_devuelve_respuestas_en_orden() -> None:
    first = make_proposal(requested=5.0)
    second = make_proposal(requested=6.0)
    double = ScriptedGeminiScriptPort(responses=[first, second])

    request_a = make_request(requested=5.0)
    request_b = make_request(requested=6.0)

    assert double.propose_script(request_a) is first
    assert double.propose_script(request_b) is second
    assert double.requests == [request_a, request_b]


def test_doble_programado_lanza_excepciones_programadas() -> None:
    programmed = GeminiNotAvailableError("sin credenciales")
    double = ScriptedGeminiScriptPort(responses=[programmed])

    with pytest.raises(GeminiNotAvailableError, match="credenciales"):
        double.propose_script(make_request())


def test_doble_programado_agotado_falla_ruidosamente() -> None:
    double = ScriptedGeminiScriptPort(responses=[make_proposal()])

    double.propose_script(make_request())

    with pytest.raises(AssertionError, match="respuestas"):
        double.propose_script(make_request())


def test_fake_original_sigue_disponible() -> None:
    fake = FakeGeminiScriptPort()

    assert isinstance(fake, GeminiScriptPort)
    with pytest.raises(GeminiNotAvailableError):
        fake.propose_script(make_request())
