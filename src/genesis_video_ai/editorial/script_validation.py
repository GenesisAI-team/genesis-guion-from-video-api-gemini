"""Validación editorial de guiones propuestos por un modelo (GEN-45).

Reglas CORE sobre la salida del modelo, sin confianza ciega:

    - los tramos propuestos deben derivar del material realmente medido:
      un tramo que no esté contenido en un segmento medido es material
      inventado y se rechaza;
    - la secuencia resultante se ordena por entrada, no solapa material y
      existe dentro de la duración real del original;
    - la duración total se contrasta con la pedida: la insuficiencia se
      declara y el exceso se rechaza.

La salida del modelo entra desordenada y con redondeos: esta función ordena
y aplica una tolerancia de contención configurable; la integridad se valida
contra los segmentos medidos, nunca contra lo que el modelo afirme.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from genesis_video_ai.editorial.sequence import (
    SourceMismatchError,
    validate_segment_sequence,
)
from genesis_video_ai.models.contracts import Segment, SourceMedia


class InventedSegmentError(ValueError):
    """Un tramo propuesto no deriva del material realmente medido."""


@dataclass(frozen=True, slots=True)
class ScriptSpan:
    """Ventana temporal propuesta, sin narración: solo trazabilidad de tiempo."""

    start_s: float
    end_s: float


@dataclass(frozen=True, slots=True)
class ScriptValidation:
    """Resultado de validar los tramos propuestos."""

    ordered: tuple[ScriptSpan, ...]
    total_s: float


def validate_script_spans(
    spans: Sequence[ScriptSpan],
    *,
    source: SourceMedia,
    measured_segments: Sequence[Segment],
    requested_duration_s: float,
    tolerance_s: float = 0.0,
) -> ScriptValidation:
    """Valida los tramos propuestos contra el material medido del original.

    Args:
        spans: Tramos propuestos por el modelo, en cualquier orden.
        source: Original bajo validación.
        measured_segments: Segmentos medidos y validados en la fase de análisis.
        requested_duration_s: Duración de guion pedida.
        tolerance_s: Tolerancia de redondeo para contención y duración total.

    Returns:
        Los tramos ordenados con su duración total.

    Raises:
        ValueError: Si los parámetros numéricos no son válidos.
        SourceMismatchError: Si el material medido referencia otro original.
        DisorderedSequenceError: Nunca (la entrada se ordena aquí).
        OverlappingSegmentsError: Si dos tramos solapan material.
        OutOfBoundsError: Si un tramo excede la duración real del original.
        InsufficientMaterialError: Si la duración total se queda corta.
        ExcessMaterialError: Si la duración total se excede.
        InventedSegmentError: Si un tramo no deriva del material medido.
    """
    _check_requirements(requested_duration_s, tolerance_s)
    _check_measured_source(measured_segments, source.id)

    ordered_spans = tuple(sorted(spans, key=lambda span: span.start_s))
    _check_existing_time(ordered_spans)
    as_segments = [
        Segment(source_id=source.id, start_s=span.start_s, end_s=span.end_s)
        for span in ordered_spans
    ]
    validation = validate_segment_sequence(
        as_segments,
        source=source,
        requested_duration_s=requested_duration_s,
        tolerance_s=tolerance_s,
    )
    _check_derived_from_measured(ordered_spans, measured_segments, tolerance_s)

    return ScriptValidation(
        ordered=ordered_spans,
        total_s=validation.total_s,
    )


def _check_requirements(requested_duration_s: float, tolerance_s: float) -> None:
    if not math.isfinite(requested_duration_s) or requested_duration_s <= 0:
        msg = (
            "requested_duration_s debe ser un valor finito mayor que 0, "
            f"recibido {requested_duration_s!r}"
        )
        raise ValueError(msg)
    if not math.isfinite(tolerance_s) or tolerance_s < 0:
        msg = f"tolerance_s debe ser un valor finito no negativo, recibido {tolerance_s!r}"
        raise ValueError(msg)


def _check_existing_time(ordered_spans: Sequence[ScriptSpan]) -> None:
    """Un tramo con tiempo no finito o negativo referencia material inexistente."""
    for span in ordered_spans:
        if not math.isfinite(span.start_s) or not math.isfinite(span.end_s) or span.start_s < 0:
            msg = (
                f"El tramo [{span.start_s!r}, {span.end_s!r}) referencia material "
                "inexistente: el tiempo no puede ser negativo ni infinito"
            )
            raise InventedSegmentError(msg)


def _check_measured_source(measured_segments: Sequence[Segment], source_id: str) -> None:
    for segment in measured_segments:
        if segment.source_id != source_id:
            msg = (
                "El material medido no referencia el original "
                f"{source_id!r}: hay {segment.source_id!r}"
            )
            raise SourceMismatchError(msg)


def _check_derived_from_measured(
    ordered_spans: Sequence[ScriptSpan],
    measured_segments: Sequence[Segment],
    tolerance_s: float,
) -> None:
    for span in ordered_spans:
        contained = any(
            span.start_s >= segment.start_s - tolerance_s
            and span.end_s <= segment.end_s + tolerance_s
            for segment in measured_segments
        )
        if not contained:
            msg = (
                f"El tramo [{span.start_s!r}, {span.end_s!r}) no deriva del material "
                "medido: proponerlo sería inventar material inexistente"
            )
            raise InventedSegmentError(msg)
