"""Puerto Gemini e inyección de doble de test (GEN-36).

En esta fase solo se prepara el contrato: el cliente real (SDK ``google-genai``)
llegará en la fase siguiente. NO hay inferencia real ni simulada, ni llamadas
de red, ni facturación en ningún punto.

``FakeGeminiScriptPort`` es el doble determinista para tests: registra la
petición recibida y declara explícitamente que no genera guiones.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from genesis_video_ai.models.contracts import Segment, SourceMedia


class ScriptProposalRequest(BaseModel):
    """Petición para proponer un guion a partir del material validado."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    source: SourceMedia
    segments: tuple[Segment, ...] = Field(default=())
    requested_duration_s: float = Field(gt=0)


class ScriptProposal(BaseModel):
    """Respuesta del puerto: contrato sellado hasta la fase de generación.

    La forma de la propuesta (segmentos aceptados, narración, justificación)
    se define en la fase siguiente; aquí solo se reserva el tipo para el
    protocolo y los dobles.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")


class GeminiNotAvailableError(RuntimeError):
    """El puerto Gemini no está disponible o no está permitido usarlo."""


@runtime_checkable
class GeminiScriptPort(Protocol):
    """Puerto de generación de guiones con la API de Gemini (fase siguiente)."""

    def propose_script(self, request: ScriptProposalRequest) -> ScriptProposal:
        """Devuelve la propuesta de guion para la selección validada.

        Raises:
            GeminiNotAvailableError: Si el puerto no está operativo.
        """
        ...  # pragma: no cover - cuerpo de declaración de protocolo


class FakeGeminiScriptPort:
    """Doble del puerto: registra peticiones y nunca produce inferencia.

    El doble es deliberadamente "tonto": no simula respuestas de Gemini. La
    fase de generación introducirá sus propios dobles con respuestas
    programadas; este existe para inyectar en los flujos de fase 2.
    """

    def __init__(self) -> None:
        self.requests: list[ScriptProposalRequest] = []

    def propose_script(self, request: ScriptProposalRequest) -> ScriptProposal:
        """Registra la petición y declara indisponibilidad de inferencia."""
        self.requests.append(request)
        msg = (
            "El fake de Gemini no realiza inferencia real ni simulada: "
            "la generación de guiones llega en la fase siguiente"
        )
        raise GeminiNotAvailableError(msg)
