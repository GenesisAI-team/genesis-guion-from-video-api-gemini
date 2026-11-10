"""Tests de los contratos Pydantic compartidos (GEN-36 §2)."""

from __future__ import annotations

import math
from pathlib import Path
from typing import get_args
from uuid import UUID

import pytest
from pydantic import ValidationError

from genesis_video_ai.models.contracts import (
    MediaContainer,
    Segment,
    SourceMedia,
    StreamInfo,
    StreamKind,
)


def make_stream(**overrides: object) -> StreamInfo:
    """Factoría de una pista válida."""
    values: dict[str, object] = {
        "index": 0,
        "kind": "video",
        "codec": "h264",
        "width": 1920,
        "height": 1080,
        "fps": 25.0,
    }
    values.update(overrides)
    return StreamInfo(**values)  # type: ignore[arg-type]


def make_source(**overrides: object) -> SourceMedia:
    """Factoría de una fuente original válida."""
    values: dict[str, object] = {
        "id": "src-1",
        "path": Path("C:/medias/original.mp4"),
        "container": "mp4",
        "duration_s": 120.0,
        "size_bytes": 1024,
        "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
        "streams": (make_stream(),),
        "metadata": {"major_brand": "isom"},
    }
    values.update(overrides)
    return SourceMedia(**values)  # type: ignore[arg-type]


def make_segment(source_id: str = "src-1", **overrides: object) -> Segment:
    """Factoría de un segmento in/out válido."""
    values: dict[str, object] = {"source_id": source_id, "start_s": 5.0, "end_s": 12.5}
    values.update(overrides)
    return Segment(**values)  # type: ignore[arg-type]


# --- Segment -------------------------------------------------------------


def test_segment_expone_la_duracion_real_del_intervalo() -> None:
    segment = make_segment(start_s=2.5, end_s=10.75)

    assert segment.duration_s == pytest.approx(8.25)


def test_segment_es_inmutable() -> None:
    segment = make_segment()

    with pytest.raises(ValidationError):
        segment.start_s = 0.0


def test_segmentos_con_los_mismos_campos_son_iguales() -> None:
    first = make_segment(start_s=1.0, end_s=2.0)
    second = make_segment(start_s=1.0, end_s=2.0)

    assert first == second


def test_model_dump_de_un_segmento_hace_roundtrip() -> None:
    segment = make_segment(start_s=1.0, end_s=2.0)

    rebuilt = Segment.model_validate(segment.model_dump())

    assert rebuilt == segment


@pytest.mark.parametrize("source_id", ["", "   "])
def test_segmento_rechaza_source_id_sin_contenido(source_id: str) -> None:
    with pytest.raises(ValidationError, match="source_id"):
        make_segment(source_id=source_id)


@pytest.mark.parametrize("start_s", [-0.01, -100.0])
def test_segmento_rechaza_start_negativo(start_s: float) -> None:
    with pytest.raises(ValidationError, match="start_s"):
        make_segment(start_s=start_s)


@pytest.mark.parametrize(("start_s", "end_s"), [(5.0, 4.99), (5.0, 5.0)])
def test_segmento_vacio_o_invertido_es_rechazado(start_s: float, end_s: float) -> None:
    with pytest.raises(ValidationError, match="end_s"):
        make_segment(start_s=start_s, end_s=end_s)


def test_segmento_rechaza_valores_no_finitos() -> None:
    with pytest.raises(ValidationError):
        make_segment(start_s=math.nan)
    with pytest.raises(ValidationError):
        make_segment(end_s=math.inf)


def test_segmento_no_acepta_campos_extra() -> None:
    with pytest.raises(ValidationError):
        make_segment(duration_narrativa=3)


# --- StreamInfo ----------------------------------------------------------


def test_pista_opcional_sin_datos_explicitos() -> None:
    stream = StreamInfo(index=1, kind="other")

    assert stream.codec is None
    assert stream.width is None
    assert stream.height is None
    assert stream.fps is None
    assert stream.duration_s is None
    assert stream.language is None


def test_pista_rechaza_indice_negativo() -> None:
    with pytest.raises(ValidationError, match="index"):
        make_stream(index=-1)


def test_pista_rechaza_fps_no_positivo() -> None:
    with pytest.raises(ValidationError, match="fps"):
        make_stream(fps=0.0)


def test_pista_rechaza_resolucion_negativa() -> None:
    with pytest.raises(ValidationError, match="width"):
        make_stream(width=-1)
    with pytest.raises(ValidationError, match="height"):
        make_stream(height=0)


def test_pista_rechaza_duracion_no_positiva() -> None:
    with pytest.raises(ValidationError, match="duration_s"):
        make_stream(duration_s=0.0)


@pytest.mark.parametrize("kind", ["video", "audio", "other"])
def test_tipos_de_pistas_validos(kind: StreamKind) -> None:
    stream = make_stream(kind=kind)

    assert stream.kind == kind


def test_pista_rechaza_tipo_desconocido() -> None:
    with pytest.raises(ValidationError):
        make_stream(kind="subtitles")


# --- SourceMedia ---------------------------------------------------------


def test_fuente_valida_con_datos_consistentes() -> None:
    source = make_source()

    assert source.id == "src-1"
    assert source.container == "mp4"
    assert source.duration_s == pytest.approx(120.0)
    assert len(source.streams) == 1
    assert source.metadata == {"major_brand": "isom"}


def test_fuente_requiere_campos_minimos() -> None:
    source = SourceMedia(
        id="src-2",
        path=Path("C:/medias/original.mov"),
        container="mov",
        duration_s=8.0,
        size_bytes=1,
        format_name="mov,mp4,m4a,3gp,3g2,mj2",
    )

    assert source.streams == ()
    assert source.metadata == {}


def test_fuente_sin_id_genera_identificadores_unicos() -> None:
    kwargs: dict[str, object] = {
        "path": Path("C:/medias/original.mp4"),
        "container": "mp4",
        "duration_s": 8.0,
        "size_bytes": 1,
        "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
    }
    first = SourceMedia(**kwargs)  # type: ignore[arg-type]
    second = SourceMedia(**kwargs)  # type: ignore[arg-type]

    # los identificadores autogenerados son UUID, base de las referencias
    # trazables de los segmentos al original
    UUID(first.id)
    UUID(second.id)
    assert first.id != second.id


def test_fuente_acepta_los_contenedores_declarados() -> None:
    for container in get_args(MediaContainer):
        media = make_source(container=container)

        assert media.container == container


def test_fuente_rechaza_contenedor_desconocido() -> None:
    with pytest.raises(ValidationError):
        make_source(container="mkv")


@pytest.mark.parametrize("tail", ["original.mp4", "medias/original.mp4"])
def test_fuente_rechaza_ruta_relativa(tail: str) -> None:
    with pytest.raises(ValidationError, match="ruta"):
        make_source(path=Path(tail))


@pytest.mark.parametrize("duration_s", [0.0, -1.0, math.nan, math.inf])
def test_fuente_rechaza_duracion_invalida(duration_s: float) -> None:
    with pytest.raises(ValidationError, match="duration_s"):
        make_source(duration_s=duration_s)


def test_fuente_rechaza_peso_negativo() -> None:
    with pytest.raises(ValidationError, match="size_bytes"):
        make_source(size_bytes=-5)


def test_fuente_rechaza_formato_vacio() -> None:
    with pytest.raises(ValidationError, match="format_name"):
        make_source(format_name="")


def test_fuente_no_acepta_campos_extra() -> None:
    with pytest.raises(ValidationError):
        make_source(unknown=1)


def test_model_dump_de_una_fuente_hace_roundtrip() -> None:
    source = make_source()

    rebuilt = SourceMedia.model_validate(source.model_dump())

    assert rebuilt == source
