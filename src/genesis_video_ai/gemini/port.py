"""Puerto Gemini, dobles de test y contrato de guion trazable (GEN-36, GEN-45).

``GeminiScriptPort`` es el contrato de generación de guiones. El cliente real
(``google-genai``) vive detrás del puerto en ``client.py``; esta fase define el
contrato de la propuesta: guiones trazables con origen, tiempos in/out reales,
narración y duración calculada.

``FakeGeminiScriptPort`` declara explícitamente que no genera guiones.
``ScriptedGeminiScriptPort`` es el doble con respuestas programadas para
probar flujos sin inferencia real: nunca llama a la API ni genera coste.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from genesis_video_ai.gemini.errors import GeminiNotAvailableError
from genesis_video_ai.models.contracts import Segment, SourceMedia

__all__ = [
    "FakeGeminiScriptPort",
    "GeminiNotAvailableError",
    "GeminiScriptPort",
    "ScriptEntry",
    "ScriptProposal",
    "ScriptProposalRequest",
    "ScriptedGeminiScriptPort",
]


class ScriptProposalRequest(BaseModel):
    """Petición para proponer un guion a partir del material validado."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    source: SourceMedia
    segments: tuple[Segment, ...] = Field(default=())
    requested_duration_s: float = Field(gt=0)


class ScriptEntry(BaseModel):
    """Un tramo del guion: ventana real del original más su narración.

    La trazabilidad exige que ``start_s``/``end_s`` referencien material
    realmente grabado; la validación crítica vive en ``editorial/``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    source_id: str = Field(min_length=1)
    start_s: float = Field(ge=0)
    end_s: float
    narration: str = Field(min_length=1)
    justification: str = ""

    @field_validator("narration")
    @classmethod
    def _narracion_con_contenido(cls, value: str) -> str:
        """La narración no puede ser ruido en blanco."""
        if not value.strip():
            msg = "narration debe contener texto con contenido"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def _ventana_coherente(self) -> ScriptEntry:
        """La ventana debe contener tiempo positivo."""
        if self.end_s <= self.start_s:
            msg = f"end_s ({self.end_s!r}) debe ser mayor que start_s ({self.start_s!r})"
            raise ValueError(msg)
        return self

    @property
    def duration_s(self) -> float:
        """Duración real del tramo en segundos."""
        return self.end_s - self.start_s


class ScriptProposal(BaseModel):
    """Guion propuesto: tramos ordenados y trazables al original.

    Cada entrada referencia el mismo original; la duración total se calcula
    siempre de las entradas, nunca se confía en un valor externo.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    source_id: str = Field(min_length=1)
    requested_duration_s: float = Field(gt=0)
    entries: tuple[ScriptEntry, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _entradas_del_mismo_origen(self) -> ScriptProposal:
        """Todas las entradas deben referenciar el original de la propuesta."""
        ajenas = [entry for entry in self.entries if entry.source_id != self.source_id]
        if ajenas:
            ids = ", ".join(sorted({entry.source_id for entry in ajenas}))
            msg = f"Las entradas no referencian el original {self.source_id!r}: {ids}"
            raise ValueError(msg)
        return self

    @property
    def total_duration_s(self) -> float:
        """Duración total calculada de las entradas, en segundos."""
        return sum(entry.duration_s for entry in self.entries)


@runtime_checkable
class GeminiScriptPort(Protocol):
    """Puerto de generación de guiones con la API de Gemini."""

    def propose_script(self, request: ScriptProposalRequest) -> ScriptProposal:
        """Devuelve la propuesta de guion para la selección validada.

        Raises:
            GeminiNotAvailableError: Si el puerto no está operativo.
        """
        ...  # pragma: no cover - cuerpo de declaración de protocolo


class FakeGeminiScriptPort:
    """Doble del puerto: registra peticiones y nunca produce inferencia.

    El doble es deliberadamente "tonto": no simula respuestas de Gemini. Para
    respuestas programadas, usar :class:`ScriptedGeminiScriptPort`.
    """

    def __init__(self) -> None:
        self.requests: list[ScriptProposalRequest] = []

    def propose_script(self, request: ScriptProposalRequest) -> ScriptProposal:
        """Registra la petición y declara indisponibilidad de inferencia."""
        self.requests.append(request)
        msg = (
            "El fake de Gemini no realiza inferencia real ni simulada: "
            "usa ScriptedGeminiScriptPort para respuestas programadas"
        )
        raise GeminiNotAvailableError(msg)


class ScriptedGeminiScriptPort:
    """Doble del puerto con respuestas programadas, sin llamada real.

    Devuelve las respuestas en orden; un elemento de tipo ``Exception`` se
    lanza en su turno. Al agotarse, falla de forma ruidosa: nunca inventa
    respuestas adicionales.
    """

    def __init__(self, responses: Sequence[ScriptProposal | Exception]) -> None:
        self._responses: list[ScriptProposal | Exception] = list(responses)
        self.requests: list[ScriptProposalRequest] = []

    def propose_script(self, request: ScriptProposalRequest) -> ScriptProposal:
        """Sirve la siguiente respuesta programada para la petición."""
        self.requests.append(request)
        if not self._responses:
            msg = "El doble programado no tiene más respuestas"
            raise AssertionError(msg)
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
