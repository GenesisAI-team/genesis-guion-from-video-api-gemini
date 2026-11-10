"""Configuración declarativa del cliente Gemini (GEN-45).

La clave se inyecta desde el entorno (``GEMINI_API_KEY`` o ``GOOGLE_API_KEY``)
y se guarda como ``SecretStr``: nunca aparece en logs, reprs ni repositorio.
Sin clave configurada, el cliente real declara indisponibilidad de forma
controlada; ninguna ejecución real ocurre sin opt-in manual.
"""

from __future__ import annotations

import os

from pydantic import BaseModel, ConfigDict, Field, SecretStr

ENV_KEYS: tuple[str, ...] = ("GEMINI_API_KEY", "GOOGLE_API_KEY")


class GeminiClientConfig(BaseModel):
    """Parámetros de conexión y límites del cliente Gemini real."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    model: str = Field(default="gemini-2.5-flash", min_length=1)
    timeout_s: float = Field(default=120.0, gt=0)
    max_output_tokens: int | None = Field(default=None, ge=1)
    temperature: float | None = Field(default=None, ge=0, le=2)
    tolerance_s: float = Field(default=0.05, ge=0)
    api_key: SecretStr | None = None

    @classmethod
    def from_env(cls) -> GeminiClientConfig:
        """Construye la configuración leyendo la clave de las variables de entorno."""
        for env_name in ENV_KEYS:
            value = os.environ.get(env_name)
            if value:
                return cls(api_key=SecretStr(value))
        return cls()
