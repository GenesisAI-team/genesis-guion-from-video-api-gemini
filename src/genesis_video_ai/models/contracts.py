"""Contratos Pydantic compartidos (fase 2, GEN-36).

Modelos de datos para el material original, sus pistas y los segmentos
in/out que referencian al original. Son contratos de shape: las reglas de
negocio (orden, integridad, duración total) viven en ``editorial/``.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

type MediaContainer = Literal["mov", "mp4"]
type StreamKind = Literal["video", "audio", "other"]


class StreamInfo(BaseModel):
    """Una pista (stream) del archivo original."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    index: int = Field(ge=0)
    kind: StreamKind
    codec: str | None = None
    duration_s: float | None = Field(default=None, gt=0)
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)
    fps: float | None = Field(default=None, gt=0)
    language: str | None = None


class SourceMedia(BaseModel):
    """Fuente original analizada, nunca modificada ni reubicada.

    ``id`` identifica la fuente de forma estable durante la sesión: los
    segmentos referencian el original a través de ``source_id``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    id: str = Field(default_factory=lambda: str(uuid4()), min_length=1)
    path: Path
    container: MediaContainer
    duration_s: float = Field(gt=0)
    size_bytes: int = Field(ge=0)
    format_name: str = Field(min_length=1)
    streams: tuple[StreamInfo, ...] = Field(default=())
    metadata: Mapping[str, str] = Field(default_factory=dict)

    @field_validator("path")
    @classmethod
    def _ruta_absoluta(cls, value: Path) -> Path:
        """El original se referencia por su ruta absoluta, nunca se copia."""
        if not value.is_absolute():
            msg = f"La ruta del original debe ser absoluta, recibida {str(value)!r}"
            raise ValueError(msg)
        return value


class Segment(BaseModel):
    """Segmento in/out sobre material realmente grabado del original."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    source_id: str
    start_s: float = Field(ge=0)
    end_s: float

    @model_validator(mode="after")
    def _segmento_coherente(self) -> Segment:
        """El intervalo debe estar anclado a un original y contener tiempo."""
        if not self.source_id.strip():
            msg = "source_id debe identificar el original, recibido vacío"
            raise ValueError(msg)
        if self.end_s <= self.start_s:
            msg = f"end_s ({self.end_s!r}) debe ser mayor que start_s ({self.start_s!r})"
            raise ValueError(msg)
        return self

    @property
    def duration_s(self) -> float:
        """Duración real del segmento en segundos."""
        return self.end_s - self.start_s
