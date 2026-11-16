"""Grounding: material real con el que se ancla la narración (GEN-45).

AGENTS.md prohíbe inventar escenas o declaraciones; el modelo solo puede
narrar lo que recibe como evidencia. Este módulo define el puerto de
grounding y el material (archivos y anotaciones de contenido) que el cliente
reúne antes de generar. Infraestructura: no decide nada editorial.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from genesis_video_ai.gemini.port import ScriptProposalRequest

__all__ = [
    "ContentAnnotation",
    "GroundingMaterial",
    "GroundingPort",
    "SourceMediaGrounding",
]


class ContentAnnotation(BaseModel):
    """Anotación de contenido real del original dentro de una ventana."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    start_s: float = Field(ge=0)
    end_s: float
    kind: str = Field(min_length=1)
    text: str = Field(min_length=1)

    @field_validator("text")
    @classmethod
    def _texto_con_contenido(cls, value: str) -> str:
        """La anotación no puede ser ruido en blanco."""
        if not value.strip():
            msg = "text debe contener texto con contenido"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def _ventana_coherente(self) -> ContentAnnotation:
        """La anotación debe cubrir tiempo positivo dentro del original."""
        if self.end_s <= self.start_s:
            msg = f"end_s ({self.end_s!r}) debe ser mayor que start_s ({self.start_s!r})"
            raise ValueError(msg)
        return self


class GroundingMaterial(BaseModel):
    """Material real disponible para anclar la narración.

    Sin archivos ni anotaciones no hay evidencia que adjuntar y el cliente
    debe rechazar generar (``MissingGroundingError``).
    """

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    media: tuple[Path, ...] = Field(default=())
    annotations: tuple[ContentAnnotation, ...] = Field(default=())

    @property
    def is_empty(self) -> bool:
        """True cuando no hay ninguna evidencia que adjuntar."""
        return not self.media and not self.annotations


@runtime_checkable
class GroundingPort(Protocol):
    """Puerto que reúne el material real del original antes de generar."""

    def collect(self, request: ScriptProposalRequest) -> GroundingMaterial:
        """Devuelve la evidencia real disponible para la petición."""
        ...  # pragma: no cover - cuerpo de declaración de protocolo


class SourceMediaGrounding:
    """Grounding real por defecto: el archivo original medido, si existe."""

    def collect(self, request: ScriptProposalRequest) -> GroundingMaterial:
        """Adjunta el original cuando está en disco; si no, no hay material."""
        if not request.source.path.is_file():
            return GroundingMaterial()
        return GroundingMaterial(media=(request.source.path,))
