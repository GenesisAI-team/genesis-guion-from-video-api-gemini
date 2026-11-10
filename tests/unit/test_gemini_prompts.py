"""Tests del constructor de prompts del cliente Gemini (GEN-45).

El prompt es infraestructura determinista: describe el material medido y el
formato JSON esperado; las reglas editoriales viven en ``editorial/``.
"""

from __future__ import annotations

from helpers import make_request, make_segment, make_source

from genesis_video_ai.gemini.port import ScriptProposalRequest
from genesis_video_ai.gemini.prompts import build_script_prompt


def test_prompt_muestra_el_original_y_su_duracion_real() -> None:
    prompt = build_script_prompt(make_request())

    assert "src-1" in prompt
    assert "42.5" in prompt
    assert "mp4" in prompt


def test_prompt_lista_el_material_medido_con_sus_tiempos() -> None:
    request = ScriptProposalRequest(
        source=make_source(duration_s=100.0),
        segments=(
            make_segment(start_s=0.0, end_s=10.0),
            make_segment(start_s=25.0, end_s=35.5),
        ),
        requested_duration_s=20.5,
    )

    prompt = build_script_prompt(request)

    assert "[0.0, 10.0]" in prompt
    assert "[25.0, 35.5]" in prompt
    assert "20.5" in prompt


def test_prompt_exige_json_con_los_campos_del_esquema() -> None:
    prompt = build_script_prompt(make_request())

    assert "JSON" in prompt
    assert "start_s" in prompt
    assert "end_s" in prompt
    assert "narration" in prompt


def test_prompt_prohibe_inventar_material() -> None:
    prompt = build_script_prompt(make_request())

    assert "invent" in prompt.lower()


def test_prompt_es_determinista() -> None:
    request = make_request()

    assert build_script_prompt(request) == build_script_prompt(request)


def test_prompt_no_incluye_credenciales() -> None:
    prompt = build_script_prompt(make_request())

    assert "api_key" not in prompt.lower()
    assert "AIza" not in prompt
