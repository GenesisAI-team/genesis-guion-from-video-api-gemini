"""Validadores editoriales puros sobre la secuencia de segmentos (GEN-36).

Reglas CORE sobre segmentos que referencian material original:
    - integridad: todos los segmentos apuntan al mismo original y a la fuente
      bajo validación; no solapan; existen dentro de la duración real.
    - orden: la secuencia se recorre en el orden temporal del original.
    - duración total: coherente con la duración pedida (insuficiencia se
      declara, exceso se rechaza).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from genesis_video_ai.models.contracts import Segment, SourceMedia


class SequenceError(ValueError):
    """Base de las violaciones de la reglas de la secuencia editorial."""


class MixedSourcesError(SequenceError):
    """Los segmentos mezclan varios orígenes distintos."""


class SourceMismatchError(SequenceError):
    """Los segmentos no referencian la fuente que se está validando."""


class DisorderedSequenceError(SequenceError):
    """La secuencia no está ordenada por segundo de entrada."""


class OverlappingSegmentsError(SequenceError):
    """Dos segmentos de la secuencia solapan material."""


class OutOfBoundsError(SequenceError):
    """Un segmento apunta más allá de la duración real del original."""


class InsufficientMaterialError(SequenceError):
    """El material seleccionado no cubre la duración pedida."""


class ExcessMaterialError(SequenceError):
    """El material seleccionado supera la duración pedida."""


@dataclass(frozen=True, slots=True)
class SequenceValidation:
    """Resultado de validar la secuencia."""

    ordered: tuple[Segment, ...]
    total_s: float


def order_segments_by_start(segments: Sequence[Segment]) -> tuple[Segment, ...]:
    """Devuelve los segmentos ordenados por su segundo de entrada (copia pura)."""
    return tuple(sorted(segments, key=lambda segment: segment.start_s))


def validate_segment_sequence(
    segments: Sequence[Segment],
    *,
    source: SourceMedia,
    requested_duration_s: float,
    tolerance_s: float = 0.0,
) -> SequenceValidation:
    """Valida la secuencia completa contra el original y la duración pedida.

    Args:
        segments: Segmentos ya ordenados temporalmente (ver
            ``order_segments_by_start``).
        source: Original bajo validación.
        requested_duration_s: Duración de guion pedida.
        tolerance_s: Tolerancia de redondeo sobre la duración total.

    Returns:
        La secuencia validada con su orden total.

    Raises:
        ValueError: Si ``requested_duration_s`` o ``tolerance_s`` no son válidos.
        MixedSourcesError: Si los segmentos mezclan varios orígenes.
        SourceMismatchError: Si no referencian la fuente dada.
        DisorderedSequenceError: Si no están ordenados por entrada.
        OverlappingSegmentsError: Si solapan material.
        OutOfBoundsError: Si exceden la duración real del original.
        InsufficientMaterialError: Si la duración total se queda corta.
        ExcessMaterialError: Si la duración total se excede.
    """
    _check_requirements(requested_duration_s, tolerance_s)
    _check_single_source(segments, source.id)
    _check_in_order(segments)
    _check_disjoint(segments)
    _check_within_source(segments, source.duration_s)

    total_s = sum(segment.duration_s for segment in segments)
    _check_total_duration(total_s, requested_duration_s, tolerance_s)

    return SequenceValidation(ordered=order_segments_by_start(segments), total_s=total_s)


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


def _check_single_source(segments: Sequence[Segment], source_id: str) -> None:
    ids = {segment.source_id for segment in segments}
    if len(ids) > 1:
        msg = f"Los segmentos mezclan varios orígenes: {', '.join(sorted(ids))}"
        raise MixedSourcesError(msg)
    if ids and ids != {source_id}:
        (used_id,) = ids
        msg = f"Los segmentos no referencian la fuente {source_id}; hay {used_id}"
        raise SourceMismatchError(msg)


def _check_in_order(segments: Sequence[Segment]) -> None:
    for index in range(1, len(segments)):
        previous = segments[index - 1]
        current = segments[index]
        if current.start_s < previous.start_s:
            msg = (
                "La secuencia debe estar ordenada por entrada: "
                f"[{previous.start_s!r}, {previous.end_s!r}) precede a "
                f"[{current.start_s!r}, {current.end_s!r})"
            )
            raise DisorderedSequenceError(msg)


def _check_disjoint(segments: Sequence[Segment]) -> None:
    for index in range(1, len(segments)):
        previous = segments[index - 1]
        current = segments[index]
        if current.start_s < previous.end_s:
            msg = (
                "Los segmentos solapan: "
                f"[{previous.start_s!r}, {previous.end_s!r}) contra "
                f"[{current.start_s!r}, {current.end_s!r})"
            )
            raise OverlappingSegmentsError(msg)


def _check_within_source(segments: Sequence[Segment], media_duration_s: float) -> None:
    for segment in segments:
        if segment.end_s > media_duration_s:
            msg = (
                f"El segmento [{segment.start_s!r}, {segment.end_s!r}) excede la "
                f"duración real del original ({media_duration_s!r} s): el material no existe"
            )
            raise OutOfBoundsError(msg)


def _check_total_duration(
    total_s: float,
    requested_duration_s: float,
    tolerance_s: float,
) -> None:
    if total_s < requested_duration_s - tolerance_s:
        msg = (
            "material insuficiente para la duración pedida: "
            f"total ({total_s!r}) menor que ({requested_duration_s!r} s)"
        )
        raise InsufficientMaterialError(msg)
    if total_s > requested_duration_s + tolerance_s:
        msg = (
            "material excesivo para la duración pedida: "
            f"total ({total_s!r}) mayor que ({requested_duration_s!r} s)"
        )
        raise ExcessMaterialError(msg)
