"""Tests del constructor de prompts del cliente Gemini (GEN-45).

El prompt es infraestructura determinista: describe el original, el material
real adjunto (grounding), el material medido y el formato JSON esperado; las
reglas editoriales viven en ``editorial/``.
"""

from __future__ import annotations

from helpers import make_material, make_request, make_segment, make_source

from genesis_video_ai.gemini.grounding import ContentAnnotation
from genesis_video_ai.gemini.port import ScriptProposalRequest
from genesis_video_ai.gemini.prompts import build_script_prompt


def test_prompt_muestra_el_original_y_su_duracion_real() -> None:
    prompt = build_script_prompt(make_request(), make_material())

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

    prompt = build_script_prompt(request, make_material())

    assert "[0.0, 10.0]" in prompt
    assert "[25.0, 35.5]" in prompt
    assert "20.5" in prompt


def test_prompt_exige_json_con_los_campos_del_esquema() -> None:
    prompt = build_script_prompt(make_request(), make_material())

    assert "JSON" in prompt
    assert "start_s" in prompt
    assert "end_s" in prompt
    assert "narration" in prompt


def test_prompt_prohibe_inventar_material() -> None:
    prompt = build_script_prompt(make_request(), make_material())

    assert "invent" in prompt.lower()


def test_prompt_es_determinista() -> None:
    request = make_request()
    material = make_material()

    assert build_script_prompt(request, material) == build_script_prompt(request, material)


def test_prompt_no_incluye_credenciales() -> None:
    prompt = build_script_prompt(make_request(), make_material())

    assert "api_key" not in prompt.lower()
    assert "AIza" not in prompt


# --- material real y anotaciones (grounding) -----------------------------------


def test_prompt_describe_el_material_real_adjunto() -> None:
    prompt = build_script_prompt(make_request(), make_material())

    assert "Material real" in prompt
    assert "original.mp4" in prompt


def test_prompt_incluye_las_anotaciones_de_contenido() -> None:
    material = make_material(
        annotations=(
            ContentAnnotation(
                start_s=0.0,
                end_s=10.0,
                kind="transcripcion",
                text="Saludo inicial del presentador.",
            ),
        )
    )

    prompt = build_script_prompt(make_request(), material)

    assert "transcripcion" in prompt
    assert "Saludo inicial del presentador." in prompt
    assert "[0.0, 10.0]" in prompt


def test_prompt_declara_la_ausencia_de_anotaciones() -> None:
    prompt = build_script_prompt(make_request(), make_material())

    assert "anotaciones" in prompt.lower()
    assert "ninguna" in prompt.lower()


def test_prompt_exige_narracion_anclada_al_material_real() -> None:
    prompt = build_script_prompt(make_request(), make_material())

    assert "material real adjunto" in prompt.lower()
    assert "no inventes escenas" in prompt.lower()
