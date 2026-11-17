"""El worker de UI ejecuta un trabajo en un QThread y publica el resultado (GEN-50)."""

from __future__ import annotations

from ui_helpers import esperar_hasta

from genesis_video_ai.jobs.flow import JobResult
from genesis_video_ai.ui.workers import ScriptJobWorker


def test_worker_ejecuta_el_trabajo_y_publica_el_resultado(qapp) -> None:
    resultados: list[JobResult] = []
    worker = ScriptJobWorker(lambda: JobResult(outcome="done"))
    worker.job_finished.connect(resultados.append)

    worker.start()
    esperar_hasta(qapp, lambda: bool(resultados))

    assert resultados == [JobResult(outcome="done")]


def test_worker_convierte_un_fallo_inesperado_en_resultado_failed(qapp) -> None:
    resultados: list[JobResult] = []

    def romper() -> JobResult:
        raise ValueError("fallo inesperado")

    worker = ScriptJobWorker(romper)
    worker.job_finished.connect(resultados.append)

    worker.start()
    esperar_hasta(qapp, lambda: bool(resultados))

    assert resultados[0].outcome == "failed"
    assert isinstance(resultados[0].error, ValueError)
    worker.wait()


def test_worker_termina_por_si_solo(qapp) -> None:
    worker = ScriptJobWorker(lambda: JobResult(outcome="done"))

    worker.start()
    esperar_hasta(qapp, lambda: not worker.isRunning())

    worker.wait()
    assert not worker.isRunning()
