"""Rangos temporales sobre material original.

Reglas CORE del MVP: una referencia de montaje solo es válida si sus tiempos
existen realmente en el archivo de origen. Ningún guion puede apuntar fuera del
material grabado.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TimeRange:
    """Intervalo semiabierto ``[start_s, end_s)`` dentro de un archivo original."""

    start_s: float
    end_s: float

    @property
    def duration_s(self) -> float:
        """Duración real del intervalo en segundos."""
        return self.end_s - self.start_s


def validate_time_range(
    start_s: float,
    end_s: float,
    *,
    media_duration_s: float,
) -> TimeRange:
    """Valida un intervalo contra la duración real del archivo de origen.

    Args:
        start_s: Segundo de entrada.
        end_s: Segundo de salida (exclusivo).
        media_duration_s: Duración total del archivo original.

    Returns:
        El intervalo validado.

    Raises:
        ValueError: Si algún valor no es finito, si ``start_s`` es negativo, si
            el intervalo está vacío o invertido, o si excede el material
            disponible.
    """
    if not math.isfinite(media_duration_s):
        msg = f"media_duration_s debe ser finito, recibido {media_duration_s!r}"
        raise ValueError(msg)
    if media_duration_s <= 0:
        msg = f"media_duration_s debe ser mayor que 0, recibido {media_duration_s!r}"
        raise ValueError(msg)
    if not math.isfinite(start_s):
        msg = f"start_s debe ser finito, recibido {start_s!r}"
        raise ValueError(msg)
    if not math.isfinite(end_s):
        msg = f"end_s debe ser finito, recibido {end_s!r}"
        raise ValueError(msg)
    if start_s < 0:
        msg = f"start_s no puede ser negativo, recibido {start_s!r}"
        raise ValueError(msg)
    if end_s <= start_s:
        msg = f"end_s ({end_s!r}) debe ser mayor que start_s ({start_s!r})"
        raise ValueError(msg)
    if end_s > media_duration_s:
        msg = (
            f"end_s ({end_s!r}) excede media_duration_s ({media_duration_s!r}): "
            "el material no existe"
        )
        raise ValueError(msg)

    return TimeRange(start_s=start_s, end_s=end_s)
