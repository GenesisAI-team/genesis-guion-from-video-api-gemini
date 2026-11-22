"""Worker de UI: ejecuta un trabajo fuera del hilo de interfaz (GEN-50).

Un QThread mínimo: recibe el trabajo como una llamada (el controlador de
``jobs.flow``) y publica el resultado por señal. El hilo de interfaz nunca
se bloquea y los errores inesperados se convierten en un resultado ``failed``
en lugar de tumbar la aplicación.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from PySide6.QtCore import QThread, Signal

if TYPE_CHECKING:
    from genesis_video_ai.jobs.flow import JobResult

JobRunner = Callable[[], "JobResult"]


class ScriptJobWorker(QThread):
    """Ejecuta el trabajo del controlador y publica su resultado."""

    job_finished = Signal(object)

    def __init__(self, runner: JobRunner, parent: object | None = None) -> None:
        super().__init__(parent)
        self._runner = runner

    def run(self) -> None:
        """Ejecuta el trabajo y publica el resultado, incluso si falla."""
        from genesis_video_ai.jobs.flow import JobResult

        try:
            result = self._runner()
        except Exception as exc:  # el worker nunca tumba la interfaz
            result = JobResult(outcome="failed", error=exc)
        self.job_finished.emit(result)
