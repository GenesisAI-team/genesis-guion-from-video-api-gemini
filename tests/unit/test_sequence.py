"""Tests CORE de los validadores editoriales de la secuencia (GEN-36 §2)."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from genesis_video_ai.editorial.sequence import (
    DisorderedSequenceError,
    ExcessMaterialError,
    InsufficientMaterialError,
    MixedSourcesError,
    OutOfBoundsError,
    OverlappingSegmentsError,
    SequenceError,
    SourceMismatchError,
    order_segments_by_start,
    validate_segment_sequence,
)
from genesis_video_ai.models.contracts import Segment, SourceMedia


def make_source(duration_s: float = 60.0, id: str = "src-1") -> SourceMedia:
    """Factoría de una fuente original para los escenarios de secuencia."""
    return SourceMedia(
        id=id,
        path=Path(f"C:/medias/{id}.mp4"),
        container="mp4",
        duration_s=duration_s,
        size_bytes=2048,
        format_name="mov,mp4,m4a,3gp,3g2,mj2",
    )


def make_segment(
    start_s: float,
    end_s: float,
    *,
    source_id: str = "src-1",
) -> Segment:
    """Factoría de un segmento que referencia al original."""
    return Segment(source_id=source_id, start_s=start_s, end_s=end_s)


def test_secuencia_valida_devuelve_orden_y_duracion_total() -> None:
    source = make_source(duration_s=60.0)
    segments = [
        make_segment(10.0, 22.5),
        make_segment(30.0, 39.0),
    ]

    result = validate_segment_sequence(
        segments,
        source=source,
        requested_duration_s=21.5,
    )

    assert result.ordered == tuple(segments)
    assert result.total_s == pytest.approx(21.5)


def test_excepciones_de_secuencia_son_value_error_clasificado() -> None:
    for error_type in (
        DisorderedSequenceError,
        ExcessMaterialError,
        InsufficientMaterialError,
        MixedSourcesError,
        OutOfBoundsError,
        OverlappingSegmentsError,
        SourceMismatchError,
    ):
        assert issubclass(error_type, SequenceError)
    assert issubclass(SequenceError, ValueError)


def test_segmentos_de_origenes_distintos_rechazados() -> None:
    segments = [
        make_segment(0.0, 5.0, source_id="src-1"),
        make_segment(10.0, 15.0, source_id="src-2"),
    ]

    with pytest.raises(MixedSourcesError, match="src-1"):
        validate_segment_sequence(segments, source=make_source(), requested_duration_s=10.0)


def test_segmentos_que_no_referencian_a_la_fuente_rechazados() -> None:
    segments = [make_segment(0.0, 5.0, source_id="src-otro")]

    with pytest.raises(SourceMismatchError, match="src-otro"):
        validate_segment_sequence(segments, source=make_source(), requested_duration_s=5.0)


def test_secuencia_desordenada_rechazada() -> None:
    segments = [
        make_segment(20.0, 25.0),
        make_segment(0.0, 10.0),
    ]

    with pytest.raises(DisorderedSequenceError, match="ordenada"):
        validate_segment_sequence(segments, source=make_source(), requested_duration_s=15.0)


def test_segmentos_solapados_rechazados() -> None:
    segments = [
        make_segment(0.0, 10.0),
        make_segment(5.0, 12.0),
    ]

    with pytest.raises(OverlappingSegmentsError, match="solapan"):
        validate_segment_sequence(segments, source=make_source(), requested_duration_s=15.0)


def test_segmentos_que_se_tocan_son_validos() -> None:
    segments = [
        make_segment(0.0, 10.0),
        make_segment(10.0, 20.0),
    ]

    result = validate_segment_sequence(
        segments, source=make_source(duration_s=30.0), requested_duration_s=20.0
    )

    assert result.total_s == pytest.approx(20.0)


def test_segmento_fuera_de_la_duracion_real_rechazado() -> None:
    segments = [make_segment(55.0, 61.0)]

    with pytest.raises(OutOfBoundsError, match="61"):
        validate_segment_sequence(
            segments, source=make_source(duration_s=60.0), requested_duration_s=5.0
        )


def test_material_insuficiente_se_declara() -> None:
    segments = [make_segment(0.0, 4.0)]

    with pytest.raises(InsufficientMaterialError, match="menor"):
        validate_segment_sequence(segments, source=make_source(), requested_duration_s=10.0)


def test_material_excesivo_rechazado() -> None:
    segments = [make_segment(0.0, 12.0)]

    with pytest.raises(ExcessMaterialError, match="mayor"):
        validate_segment_sequence(segments, source=make_source(), requested_duration_s=10.0)


def test_duracion_exacta_al_pedido_es_valida() -> None:
    segments = [make_segment(0.0, 10.0)]

    result = validate_segment_sequence(segments, source=make_source(), requested_duration_s=10.0)

    assert result.total_s == pytest.approx(10.0)


def test_tolerancia_admite_redondeo_en_ambas_direcciones() -> None:
    source = make_source(duration_s=60.0)

    insufficient = validate_segment_sequence(
        [make_segment(0.0, 9.99)],
        source=source,
        requested_duration_s=10.0,
        tolerance_s=0.01,
    )
    excessive = validate_segment_sequence(
        [make_segment(0.0, 10.01)],
        source=source,
        requested_duration_s=10.0,
        tolerance_s=0.01,
    )

    assert insufficient.total_s == pytest.approx(9.99)
    assert excessive.total_s == pytest.approx(10.01)


def test_tolerancia_cero_mantiene_valores_estrictos() -> None:
    source = make_source(duration_s=60.0)

    with pytest.raises(InsufficientMaterialError):
        validate_segment_sequence(
            [make_segment(0.0, 9.999)],
            source=source,
            requested_duration_s=10.0,
        )
    with pytest.raises(ExcessMaterialError):
        validate_segment_sequence(
            [make_segment(0.0, 10.001)],
            source=source,
            requested_duration_s=10.0,
        )


def test_secuencia_vacia_declara_insuficiencia() -> None:
    with pytest.raises(InsufficientMaterialError, match="insuficiente"):
        validate_segment_sequence((), source=make_source(), requested_duration_s=10.0)


@pytest.mark.parametrize("requested", [0.0, -5.0, math.nan, math.inf])
def test_duracion_pedida_invalida_rechazada(requested: float) -> None:
    with pytest.raises(ValueError, match="requested_duration_s"):
        validate_segment_sequence(
            [make_segment(0.0, 1.0)],
            source=make_source(duration_s=30.0),
            requested_duration_s=requested,
        )


@pytest.mark.parametrize("tolerance", [-0.1, math.nan, math.inf])
def test_tolerancia_invalida_rechazada(tolerance: float) -> None:
    with pytest.raises(ValueError, match="tolerance_s"):
        validate_segment_sequence(
            [make_segment(0.0, 1.0)],
            source=make_source(duration_s=30.0),
            requested_duration_s=10.0,
            tolerance_s=tolerance,
        )


# --- orden ---------------------------------------------------------------


def test_ordenar_por_segundo_de_entrada() -> None:
    segments = [
        make_segment(20.0, 25.0),
        make_segment(0.0, 10.0),
        make_segment(10.0, 15.0),
    ]

    ordered = order_segments_by_start(segments)

    assert [seg.start_s for seg in ordered] == [0.0, 10.0, 20.0]
    assert [seg.end_s for seg in ordered] == [10.0, 15.0, 25.0]


def test_ordenar_no_modifica_la_entrada() -> None:
    segments = [make_segment(20.0, 25.0), make_segment(0.0, 10.0)]

    order_segments_by_start(segments)

    assert [seg.start_s for seg in segments] == [20.0, 0.0]


def test_orden_no_debe_conocer_la_duracion_del_original_para_aplicarse() -> None:
    """El orden es una regla previa, independiente del material."""
    segments = [make_segment(40.0, 45.0), make_segment(0.0, 5.0)]

    ordered = order_segments_by_start(segments)

    assert [seg.start_s for seg in ordered] == [0.0, 40.0]


# --- integridad ------------------------------------------------------------


def test_la_secuencia_validada_es_inmutable() -> None:
    result = validate_segment_sequence(
        [make_segment(0.0, 5.0)],
        source=make_source(duration_s=30.0),
        requested_duration_s=5.0,
    )

    with pytest.raises(AttributeError):
        result.total_s = 99.0  # type: ignore[misc]


def test_un_segmento_que_empieza_en_el_final_exacto_no_existe() -> None:
    source = make_source(duration_s=30.0)

    with pytest.raises(OutOfBoundsError):
        validate_segment_sequence(
            [make_segment(0.0, 30.0), make_segment(30.0, 31.0)],
            source=source,
            requested_duration_s=31.0,
        )
