"""Tests del puerto de grounding y su material real (GEN-45).

AGENTS.md prohíbe inventar escenas o declaraciones: la narración solo puede
anclarse en material real. Nada aquí llama a la API de Gemini; solo se
comprueba la existencia de archivos de prueba en ``tmp_path``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from helpers import make_request
from pydantic import ValidationError

from genesis_video_ai.gemini.errors import GeminiNotAvailableError, MissingGroundingError
from genesis_video_ai.gemini.grounding import (
    ContentAnnotation,
    GroundingMaterial,
    GroundingPort,
    SourceMediaGrounding,
)
from genesis_video_ai.gemini.port import ScriptProposalRequest
from genesis_video_ai.models.contracts import Segment, SourceMedia


def request_con_archivo(path: Path) -> ScriptProposalRequest:
    """Petición de ejemplo cuyo original sí existe en disco."""
    source = SourceMedia(
        id="src-1",
        path=path,
        container="mp4",
        duration_s=42.5,
        size_bytes=4242,
        format_name="mp4",
    )
    return ScriptProposalRequest(
        source=source,
        segments=(Segment(source_id=source.id, start_s=0.0, end_s=10.0),),
        requested_duration_s=10.0,
    )


# --- material ------------------------------------------------------------------


def test_material_vacio_no_entrega_evidencia() -> None:
    material = GroundingMaterial()

    assert material.media == ()
    assert material.annotations == ()
    assert material.is_empty is True


def test_material_con_archivo_no_es_vacio(tmp_path: Path) -> None:
    media = tmp_path / "original.mp4"
    media.write_bytes(b"x")

    material = GroundingMaterial(media=(media,))

    assert material.is_empty is False


def test_material_con_anotaciones_no_es_vacio() -> None:
    annotation = ContentAnnotation(
        start_s=0.0,
        end_s=10.0,
        kind="transcripcion",
        text="Saludo inicial del presentador.",
    )

    material = GroundingMaterial(annotations=(annotation,))

    assert material.is_empty is False


# --- anotaciones de contenido --------------------------------------------------


def test_anotacion_acepta_ventana_coherente() -> None:
    annotation = ContentAnnotation(
        start_s=1.5,
        end_s=9.0,
        kind="escena",
        text="Plano general del estudio.",
    )

    assert annotation.end_s > annotation.start_s


@pytest.mark.parametrize(
    ("start_s", "end_s"),
    [(10.0, 10.0), (10.0, 5.0)],
)
def test_anotacion_rechaza_ventana_incoherente(start_s: float, end_s: float) -> None:
    with pytest.raises(ValidationError, match="end_s"):
        ContentAnnotation(start_s=start_s, end_s=end_s, kind="escena", text="Plano")


def test_anotacion_rechaza_texto_o_tipo_vacios() -> None:
    with pytest.raises(ValidationError, match="kind"):
        ContentAnnotation(start_s=0.0, end_s=1.0, kind="", text="Plano")
    with pytest.raises(ValidationError, match="text"):
        ContentAnnotation(start_s=0.0, end_s=1.0, kind="escena", text="   ")


# --- grounding real y protocolo ------------------------------------------------


def test_source_media_grounding_adjunta_el_archivo_real(tmp_path: Path) -> None:
    media = tmp_path / "original.mp4"
    media.write_bytes(b"x")

    material = SourceMediaGrounding().collect(request_con_archivo(media))

    assert material.media == (media,)
    assert material.is_empty is False


def test_source_media_grounding_sin_archivo_no_entrega_material() -> None:
    request = make_request()

    material = SourceMediaGrounding().collect(request)

    assert material.media == ()
    assert material.is_empty is True


def test_source_media_grounding_cumple_el_protocolo() -> None:
    assert isinstance(SourceMediaGrounding(), GroundingPort)
    assert not isinstance(object(), GroundingPort)


def test_missing_grounding_es_indisponibilidad_del_puerto() -> None:
    assert issubclass(MissingGroundingError, GeminiNotAvailableError)
