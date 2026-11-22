"""Flujo de trabajos: análisis, validación y generación con estados (GEN-50).

Conecta el análisis técnico (ffprobe), la validación editorial y el puerto
Gemini en un controlador de trabajos con estados observables, cancelación
cooperativa, errores tipados, límites de peso y limpieza garantizada de
temporales de sesión. La UI observa el mismo flujo que los tests; los dobles
sustituyen al puerto sin llamadas reales ni coste.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from genesis_video_ai.analysis.ffprobe import (
    DEFAULT_MAX_FILE_BYTES,
    DEFAULT_RUNNER,
    FFProbeRunner,
    probe_video,
)
from genesis_video_ai.editorial.sequence import (
    order_segments_by_start,
    validate_segment_sequence,
)
from genesis_video_ai.gemini.errors import GeminiCancelledError
from genesis_video_ai.gemini.port import GeminiScriptPort, ScriptProposal, ScriptProposalRequest
from genesis_video_ai.jobs.tempfiles import session_temp_dir
from genesis_video_ai.models.contracts import Segment, SourceMedia

type JobPhase = Literal["analyzing", "validating", "generating", "done", "failed", "cancelled"]
type JobOutcome = Literal["done", "failed", "cancelled"]

EventHandler = Callable[["JobEvent"], None]


@dataclass(frozen=True, slots=True)
class JobEvent:
    """Un paso observable del trabajo: fase y mensaje para la UI."""

    phase: JobPhase
    message: str = ""


@dataclass(frozen=True, slots=True)
class JobResult:
    """Resultado del trabajo: estado final y lo producido hasta entonces."""

    outcome: JobOutcome
    events: tuple[JobEvent, ...] = ()
    source: SourceMedia | None = None
    segments: tuple[Segment, ...] = ()
    proposal: ScriptProposal | None = None
    error: Exception | None = None


class ScriptJobController:
    """Controlador del flujo: análisis del original y generación del guion.

    Cada método ejecuta un paso del flujo dentro de un directorio temporal de
    sesión que se elimina al terminar, incluso si el paso falla o se cancela.
    La cancelación es cooperativa por evento y gana al resultado.
    """

    def __init__(
        self,
        script_port: GeminiScriptPort,
        *,
        cancel_event: threading.Event | None = None,
        probe_runner: FFProbeRunner = DEFAULT_RUNNER,
        max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
        tolerance_s: float = 0.05,
        on_event: EventHandler | None = None,
        temp_root: Path | str | None = None,
    ) -> None:
        """Construye el controlador; no ejecuta nada ni contacta con nada."""
        self._script_port = script_port
        self._cancel_event = cancel_event or threading.Event()
        self._probe_runner = probe_runner
        self._max_file_bytes = max_file_bytes
        self._tolerance_s = tolerance_s
        self._on_event = on_event
        self._temp_root = temp_root

    def cancel(self) -> None:
        """Solicita la parada de la operación en curso o siguiente."""
        self._cancel_event.set()

    def analyze(self, source_path: Path | str) -> JobResult:
        """Analiza el original (solo lectura) con límite de peso.

        Raises:
            Nada: todo fallo se convierte en un resultado ``failed``.
        """
        events: list[JobEvent] = []
        try:
            with self._session():
                return self._analyze(source_path, events)
        except Exception as exc:  # p. ej. fallo creando el temporal de sesión
            return self._failed(events, exc)

    def generate(
        self,
        source: SourceMedia,
        segments: Sequence[Segment],
        requested_duration_s: float,
    ) -> JobResult:
        """Valida la selección y pide el guion al puerto.

        La secuencia se ordena por entrada antes de validarse; el puerto
        recibe los segmentos medidos y validados.

        Raises:
            Nada: todo fallo se convierte en un resultado ``failed``.
        """
        events: list[JobEvent] = []
        try:
            with self._session():
                return self._generate(source, segments, requested_duration_s, events)
        except Exception as exc:  # p. ej. fallo creando el temporal de sesión
            return self._failed(events, exc)

    @contextmanager
    def _session(self) -> Iterator[None]:
        with session_temp_dir(root=self._temp_root):
            yield

    def _analyze(self, source_path: Path | str, events: list[JobEvent]) -> JobResult:
        if self._cancelled(events):
            return self._result("cancelled", events)
        self._emit(events, JobEvent("analyzing"))
        try:
            source = probe_video(
                source_path,
                runner=self._probe_runner,
                max_file_bytes=self._max_file_bytes,
            )
        except Exception as exc:
            return self._failed(events, exc)
        if self._cancelled(events):
            return self._result("cancelled", events)
        self._emit(
            events,
            JobEvent("done", f"Original medido: {source.duration_s:g} s ({source.container})"),
        )
        return JobResult("done", tuple(events), source=source)

    def _generate(
        self,
        source: SourceMedia,
        segments: Sequence[Segment],
        requested_duration_s: float,
        events: list[JobEvent],
    ) -> JobResult:
        if self._cancelled(events):
            return self._result("cancelled", events)
        self._emit(events, JobEvent("validating"))
        ordered = order_segments_by_start(tuple(segments))
        try:
            validated = validate_segment_sequence(
                ordered,
                source=source,
                requested_duration_s=requested_duration_s,
                tolerance_s=self._tolerance_s,
            )
        except Exception as exc:
            return self._failed(events, exc)
        if self._cancelled(events):
            return self._result("cancelled", events)
        self._emit(events, JobEvent("generating"))
        try:
            request = ScriptProposalRequest(
                source=source,
                segments=validated.ordered,
                requested_duration_s=requested_duration_s,
            )
            proposal = self._script_port.propose_script(request)
        except GeminiCancelledError as exc:
            self._emit(events, JobEvent("cancelled", str(exc)))
            return JobResult("cancelled", tuple(events), error=exc)
        except Exception as exc:
            return self._failed(events, exc)
        if self._cancelled(events):
            return self._result("cancelled", events)
        self._emit(events, JobEvent("done", f"Guion propuesto: {len(proposal.entries)} tramos"))
        return JobResult("done", tuple(events), proposal=proposal)

    def _cancelled(self, events: list[JobEvent]) -> bool:
        if not self._cancel_event.is_set():
            return False
        self._emit(events, JobEvent("cancelled", "La operación fue cancelada"))
        return True

    def _emit(self, events: list[JobEvent], event: JobEvent) -> None:
        events.append(event)
        if self._on_event is not None:
            self._on_event(event)

    def _failed(self, events: list[JobEvent], exc: Exception) -> JobResult:
        self._emit(events, JobEvent("failed", str(exc) or type(exc).__name__))
        return JobResult("failed", tuple(events), error=exc)

    @staticmethod
    def _result(outcome: Literal["cancelled"], events: list[JobEvent]) -> JobResult:
        return JobResult(outcome, tuple(events))
