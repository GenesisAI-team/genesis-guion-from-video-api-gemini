"""Cliente Gemini real detrás del puerto ``GeminiScriptPort`` (GEN-45).

Orquesta la generación con límites y sin confianza ciega:

    - la sesión con el SDK se construye perezosamente y se reutiliza; sin
      credencial el fallo es controlado (``GeminiNotAvailableError``);
    - la llamada corre en un hilo de trabajo con plazo configurado y
      cancelación cooperativa por evento: la cancelación gana al resultado;
    - la salida del modelo se valida contra el esquema estricto y contra las
      reglas editoriales del material medido antes de convertirse en guion;
      los segmentos inventados se rechazan y la insuficiencia se declara.

Nunca se llama a la API en tests ni en CI: la sesión se inyecta.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from genesis_video_ai.editorial.script_validation import ScriptSpan, validate_script_spans
from genesis_video_ai.gemini.config import GeminiClientConfig
from genesis_video_ai.gemini.errors import GeminiCancelledError, GeminiTimeoutError
from genesis_video_ai.gemini.port import ScriptEntry, ScriptProposal, ScriptProposalRequest
from genesis_video_ai.gemini.prompts import build_script_prompt
from genesis_video_ai.gemini.response import parse_payload
from genesis_video_ai.gemini.sdk_adapter import GoogleGenaiScriptSession

if TYPE_CHECKING:
    from collections.abc import Callable

    from genesis_video_ai.gemini.sdk_adapter import ResponseSchema

POLL_INTERVAL_S: float = 0.02


@runtime_checkable
class ScriptSession(Protocol):
    """Sesión de generación: el adaptador del SDK la implementa."""

    def generate(self, prompt: str, response_schema: ResponseSchema) -> str:
        """Genera texto estructurado para el prompt dado."""
        ...  # pragma: no cover - cuerpo de declaración de protocolo


class RealGeminiScriptPort:
    """Puerto Gemini con la API real: límites, errores tipados y cancelación."""

    def __init__(
        self,
        config: GeminiClientConfig,
        *,
        session_factory: Callable[[GeminiClientConfig], ScriptSession] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> None:
        """Construye el puerto; no se conecta ni realiza ninguna llamada."""
        self._config = config
        self._session_factory = session_factory or self._default_session_factory
        self._cancel_event = cancel_event or threading.Event()
        self._session: ScriptSession | None = None

    @staticmethod
    def _default_session_factory(config: GeminiClientConfig) -> ScriptSession:
        return GoogleGenaiScriptSession(config)

    def cancel(self) -> None:
        """Solicita la parada de la operación en curso o siguiente."""
        self._cancel_event.set()

    def propose_script(self, request: ScriptProposalRequest) -> ScriptProposal:
        """Propone un guion trazable con la API de Gemini.

        Raises:
            GeminiNotAvailableError: Si no hay credencial o el SDK falta.
            GeminiCancelledError: Si se solicitó cancelar la operación.
            GeminiTimeoutError: Si la generación excede el plazo configurado.
            GeminiQuotaExceededError: Si la API deniega por cuota.
            GeminiRequestError: Si la petición falla por otra causa.
            GeminiInvalidResponseError: Si la respuesta no cumple el esquema.
            InventedSegmentError: Si el modelo propone material no medido.
            InsufficientMaterialError: Si el material no alcanza la duración.
            ExcessMaterialError: Si el material excede la duración pedida.
        """
        self._raise_if_cancelled()
        session = self._ensure_session()
        prompt = build_script_prompt(request)
        raw = self._generate_with_limits(session, prompt)
        payload = parse_payload(raw)
        return self._build_proposal(request, payload)

    def _raise_if_cancelled(self) -> None:
        if self._cancel_event.is_set():
            msg = "La generación del guion fue cancelada"
            raise GeminiCancelledError(msg)

    def _ensure_session(self) -> ScriptSession:
        if self._session is None:
            self._session = self._session_factory(self._config)
        return self._session

    def _generate_with_limits(self, session: ScriptSession, prompt: str) -> str:
        """Ejecuta la generación con plazo y cancelación cooperativa."""
        self._raise_if_cancelled()
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="genesis-gemini")
        try:
            future = executor.submit(session.generate, prompt, self._response_schema())
            started = time.monotonic()
            while True:
                try:
                    raw = future.result(timeout=POLL_INTERVAL_S)
                    break
                except FutureTimeoutError:
                    self._raise_if_cancelled()
                    if time.monotonic() - started >= self._config.timeout_s:
                        msg = (
                            "la generación excedió el plazo configurado "
                            f"({self._config.timeout_s!r} s)"
                        )
                        raise GeminiTimeoutError(msg) from None
            self._raise_if_cancelled()
            return raw
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _response_schema(self) -> ResponseSchema:
        from genesis_video_ai.gemini.response import ScriptPayload

        return ScriptPayload

    def _build_proposal(
        self,
        request: ScriptProposalRequest,
        payload: object,
    ) -> ScriptProposal:
        """Valida los tramos propuestos y construye la propuesta trazable."""
        entries = sorted(payload.entries, key=lambda entry: (entry.start_s, entry.end_s))
        spans = [ScriptSpan(start_s=entry.start_s, end_s=entry.end_s) for entry in entries]
        validation = validate_script_spans(
            spans,
            source=request.source,
            measured_segments=request.segments,
            requested_duration_s=request.requested_duration_s,
            tolerance_s=self._config.tolerance_s,
        )
        script_entries = tuple(
            ScriptEntry(
                source_id=request.source.id,
                start_s=span.start_s,
                end_s=span.end_s,
                narration=entry.narration,
                justification=entry.justification,
            )
            for span, entry in zip(validation.ordered, entries, strict=True)
        )
        return ScriptProposal(
            source_id=request.source.id,
            requested_duration_s=request.requested_duration_s,
            entries=script_entries,
        )
