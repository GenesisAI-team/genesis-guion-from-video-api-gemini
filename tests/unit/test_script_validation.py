"""Tests de la validación editorial de guiones propuestos (GEN-45).

Reglas CORE: los tramos propuestos por el modelo solo valen si referencian
material medido del original, sin solapes ni tiempos fuera de bounds, y la
duración total se contrasta con la pedida (insuficiencia declarada).
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from genesis_video_ai.editorial.script_validation import (
    InventedSegmentError,
    ScriptSpan,
    validate_script_spans,
)
from genesis_video_ai.editorial.sequence import (
    ExcessMaterialError,
    InsufficientMaterialError,
    OverlappingSegmentsError,
    SourceMismatchError,
)
from genesis_video_ai.models.contracts import Segment, SourceMedia


def make_source(duration_s: float = 100.0) -> SourceMedia:
    """Fuente original de ejemplo."""
    return SourceMedia(
        id="src-1",
        path=Path("C:/medias/original.mp4").resolve(),
        container="mp4",
        duration_s=duration_s,
        size_bytes=4242,
        format_name="mov,mp4,m4a,3gp,3g2,mj2",
    )


def make_measured() -> tuple[Segment, ...]:
    """Material realmente medido en la fase de análisis."""
    return (
        Segment(source_id="src-1", start_s=0.0, end_s=10.0),
        Segment(source_id="src-1", start_s=10.0, end_s=25.0),
    )


def spans(*pairs: tuple[float, float]) -> list[ScriptSpan]:
    """Factoría de tramos propuestos."""
    return [ScriptSpan(start_s=start, end_s=end) for start, end in pairs]


def test_tramos_dentro_del_material_medido_son_validos() -> None:
    result = validate_script_spans(
        spans((0.0, 8.5)),
        source=make_source(),
        measured_segments=make_measured(),
        requested_duration_s=8.5,
    )

    assert result.total_s == pytest.approx(8.5)
    assert result.ordered == (ScriptSpan(start_s=0.0, end_s=8.5),)


def test_tramos_desordenados_se_ordenan_por_entrada() -> None:
    result = validate_script_spans(
        spans((12.0, 20.0), (0.0, 8.0)),
        source=make_source(),
        measured_segments=make_measured(),
        requested_duration_s=16.0,
    )

    assert [span.start_s for span in result.ordered] == [0.0, 12.0]
    assert result.total_s == pytest.approx(16.0)


def test_tramos_solapados_se_rechazan() -> None:
    with pytest.raises(OverlappingSegmentsError):
        validate_script_spans(
            spans((0.0, 6.0), (5.0, 10.0)),
            source=make_source(),
            measured_segments=make_measured(),
            requested_duration_s=11.0,
        )


def test_tramo_mas_alla_de_la_duracion_real_es_inventado() -> None:
    """Un tramo fuera de la duración del original nunca deriva de lo medido."""
    with pytest.raises(InventedSegmentError):
        validate_script_spans(
            spans((20.0, 100.5)),
            source=make_source(),
            measured_segments=make_measured(),
            requested_duration_s=80.5,
        )


def test_tramo_fuera_del_material_medido_es_inventado() -> None:
    """El hueco entre 25 s y 100 s no fue medido: proponerlo es inventar."""
    with pytest.raises(InventedSegmentError, match="material medido"):
        validate_script_spans(
            spans((30.0, 40.0)),
            source=make_source(),
            measured_segments=make_measured(),
            requested_duration_s=10.0,
        )


def test_tramo_cruzando_hueco_de_medicion_es_inventado() -> None:
    with pytest.raises(InventedSegmentError):
        validate_script_spans(
            spans((5.0, 15.0)),
            source=make_source(),
            measured_segments=(Segment(source_id="src-1", start_s=0.0, end_s=6.0),),
            requested_duration_s=10.0,
        )


def test_redondeo_del_modelo_se_tolera_dentro_del_limite() -> None:
    result = validate_script_spans(
        spans((0.02, 10.02)),
        source=make_source(),
        measured_segments=make_measured(),
        requested_duration_s=10.0,
        tolerance_s=0.05,
    )

    assert result.total_s == pytest.approx(10.0)


def test_desvio_mas_alla_de_la_tolerancia_es_inventado() -> None:
    with pytest.raises(InventedSegmentError):
        validate_script_spans(
            spans((-0.5, 9.5)),
            source=make_source(),
            measured_segments=make_measured(),
            requested_duration_s=10.0,
            tolerance_s=0.05,
        )


def test_material_insuficiente_se_declara() -> None:
    with pytest.raises(InsufficientMaterialError, match="insuficiente"):
        validate_script_spans(
            spans((0.0, 4.0)),
            source=make_source(),
            measured_segments=make_measured(),
            requested_duration_s=8.5,
        )


def test_sin_tramos_es_insuficiencia() -> None:
    with pytest.raises(InsufficientMaterialError):
        validate_script_spans(
            [],
            source=make_source(),
            measured_segments=make_measured(),
            requested_duration_s=8.5,
        )


def test_material_excesivo_se_rechaza() -> None:
    with pytest.raises(ExcessMaterialError):
        validate_script_spans(
            spans((0.0, 10.0), (10.0, 25.0)),
            source=make_source(),
            measured_segments=make_measured(),
            requested_duration_s=10.0,
        )


def test_material_medido_de_otro_origen_se_rechaza() -> None:
    alien = (Segment(source_id="src-otra", start_s=0.0, end_s=10.0),)

    with pytest.raises(SourceMismatchError):
        validate_script_spans(
            spans((0.0, 8.5)),
            source=make_source(),
            measured_segments=alien,
            requested_duration_s=8.5,
        )


def test_duracion_pedida_invalida_se_rechaza() -> None:
    with pytest.raises(ValueError, match="requested_duration_s"):
        validate_script_spans(
            spans((0.0, 8.5)),
            source=make_source(),
            measured_segments=make_measured(),
            requested_duration_s=0.0,
        )


def test_tolerancia_negativa_se_rechaza() -> None:
    with pytest.raises(ValueError, match="tolerance_s"):
        validate_script_spans(
            spans((0.0, 8.5)),
            source=make_source(),
            measured_segments=make_measured(),
            requested_duration_s=8.5,
            tolerance_s=-1.0,
        )


def test_tiempos_no_finitos_se_rechazan() -> None:
    with pytest.raises(ValueError):
        validate_script_spans(
            spans((0.0, math.inf)),
            source=make_source(),
            measured_segments=make_measured(),
            requested_duration_s=10.0,
        )
