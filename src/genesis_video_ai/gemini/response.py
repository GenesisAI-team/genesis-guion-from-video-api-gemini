"""Parseo estructurado de la salida del modelo (GEN-45).

Sin confianza ciega: el texto devuelto por la API solo entra al sistema si es
JSON válido y cumple el esquema estricto. Este mismo modelo pydantic se pasa
al SDK como ``response_schema`` para forzar la forma en origen.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from genesis_video_ai.gemini.errors import GeminiInvalidResponseError


class ScriptPayloadEntry(BaseModel):
    """Esquema estricto de un tramo devuelto por el modelo."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    start_s: float = Field(ge=0)
    end_s: float
    narration: str = Field(min_length=1)
    justification: str = ""

    @field_validator("narration")
    @classmethod
    def _narracion_con_contenido(cls, value: str) -> str:
        if not value.strip():
            msg = "narration debe contener texto con contenido"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def _ventana_coherente(self) -> ScriptPayloadEntry:
        if self.end_s <= self.start_s:
            msg = f"end_s ({self.end_s!r}) debe ser mayor que start_s ({self.start_s!r})"
            raise ValueError(msg)
        return self


class ScriptPayload(BaseModel):
    """Esquema estricto del objeto JSON completo devuelto por el modelo."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    entries: tuple[ScriptPayloadEntry, ...] = Field(default=())


def parse_payload(raw: Any) -> ScriptPayload:
    """Parsea la respuesta cruda del modelo contra el esquema estricto.

    Raises:
        GeminiInvalidResponseError: Si no es texto, no es JSON válido o no
            cumple el esquema.
    """
    if not isinstance(raw, str):
        msg = "La respuesta del modelo no es texto"
        raise GeminiInvalidResponseError(msg)
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as error:
        msg = f"La respuesta del modelo no es JSON válido: {error}"
        raise GeminiInvalidResponseError(msg) from error
    if not isinstance(data, dict):
        msg = "La respuesta del modelo debe ser un objeto JSON con 'entries'"
        raise GeminiInvalidResponseError(msg)
    try:
        return ScriptPayload.model_validate(data)
    except ValidationError as error:
        msg = f"La respuesta del modelo no cumple el esquema de la propuesta: {error}"
        raise GeminiInvalidResponseError(msg) from error
