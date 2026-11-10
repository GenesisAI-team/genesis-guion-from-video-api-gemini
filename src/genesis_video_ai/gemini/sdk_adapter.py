"""Adaptador del SDK oficial ``google-genai`` (GEN-45).

Único punto del paquete que conoce el SDK: se importa perezosamente dentro
de las llamadas, de modo que el resto del sistema funciona sin él. El
adaptador nunca reintenta ni llama solo: lo orquesta ``client.py``, que
añade plazo y cancelación.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from genesis_video_ai.gemini.config import GeminiClientConfig
from genesis_video_ai.gemini.errors import (
    GeminiAuthError,
    GeminiInvalidResponseError,
    GeminiNotAvailableError,
    GeminiQuotaExceededError,
    GeminiRequestError,
    GeminiTimeoutError,
)

if TYPE_CHECKING:
    from pydantic import BaseModel

    ResponseSchema = type[BaseModel]


def map_api_error(code: int, message: str) -> GeminiRequestError:
    """Traduce el código HTTP de la API a un error tipado del dominio."""
    if code == 429:
        return GeminiQuotaExceededError(f"cuota o límite de peticiones agotado (429): {message}")
    if code in (401, 403):
        return GeminiAuthError(f"credenciales inválidas o sin permisos ({code}): {message}")
    if code == 408:
        return GeminiTimeoutError(f"la API excedió su propio plazo (408): {message}")
    return GeminiRequestError(f"la petición a la API falló ({code}): {message}")


class GoogleGenaiScriptSession:
    """Sesión con la API de Gemini para generar una propuesta de guion."""

    def __init__(self, config: GeminiClientConfig) -> None:
        """Construye el cliente del SDK sin realizar ninguna llamada de red.

        Raises:
            GeminiNotAvailableError: Si no hay credencial o el SDK no está
                instalado.
        """
        if config.api_key is None:
            msg = (
                "no hay credencial de Gemini: define GEMINI_API_KEY en el entorno "
                "para habilitar ejecuciones reales (siempre opt-in manual)"
            )
            raise GeminiNotAvailableError(msg)
        try:
            from google import genai
            from google.genai import types
        except ImportError as error:
            msg = "el SDK google-genai no está instalado en este entorno"
            raise GeminiNotAvailableError(msg) from error

        self._config = config
        self._client = genai.Client(  # type: ignore[union-attr]
            api_key=config.api_key.get_secret_value(),
            http_options=types.HttpOptions(timeout=int(config.timeout_s * 1000)),
        )

    def generate(self, prompt: str, response_schema: ResponseSchema) -> str:
        """Genera texto estructurado para el prompt dado.

        Raises:
            GeminiQuotaExceededError: Si la API deniega por cuota.
            GeminiAuthError: Si las credenciales no son válidas.
            GeminiTimeoutError: Si la API excede su plazo.
            GeminiRequestError: Si la petición falla por otra causa.
            GeminiInvalidResponseError: Si la respuesta no trae texto.
        """
        from google.genai import errors

        request_config: dict[str, Any] = {
            "response_mime_type": "application/json",
            "response_schema": response_schema,
        }
        if self._config.max_output_tokens is not None:
            request_config["max_output_tokens"] = self._config.max_output_tokens
        if self._config.temperature is not None:
            request_config["temperature"] = self._config.temperature

        try:
            response = self._client.models.generate_content(
                model=self._config.model,
                contents=prompt,
                config=request_config,
            )
        except errors.APIError as error:
            raise map_api_error(error.code, str(error.message)) from error
        except Exception as error:
            raise GeminiRequestError(f"error del SDK de Gemini: {error}") from error

        text = getattr(response, "text", None)
        if not text:
            msg = "la respuesta del modelo está vacía o no trae texto"
            raise GeminiInvalidResponseError(msg)
        return str(text)
