"""Errores tipados del puerto Gemini (GEN-45).

Jerarquía única para todo el paquete ``gemini``: el llamador puede capturar la
base :class:`GeminiError` o afinar por causa (disponibilidad, cuota, red,
cancelación, respuesta inválida). Solo declaraciones: cero lógica ejecutable.
"""

from __future__ import annotations


class GeminiError(RuntimeError):
    """Base de todos los errores del puerto Gemini."""


class GeminiNotAvailableError(GeminiError):
    """El puerto Gemini no está disponible o no está permitido usarlo."""


class GeminiAuthError(GeminiNotAvailableError):
    """Las credenciales existen pero no son válidas o carecen de permisos."""


class GeminiQuotaExceededError(GeminiError):
    """La API rechazó la petición por cuota o límite de peticiones (429)."""


class GeminiRequestError(GeminiError):
    """La petición a la API falló por una causa no clasificada."""


class GeminiTimeoutError(GeminiRequestError):
    """La petición superó el plazo configurado."""


class GeminiCancelledError(GeminiError):
    """La operación se canceló antes de completarse."""


class GeminiInvalidResponseError(GeminiError):
    """La respuesta del modelo no es JSON válido o no cumple el esquema."""
