"""Ventana principal PySide6: vídeo → guion → exportación (GEN-50).

La ventana solo orquesta: el comportamiento del trabajo vive en
``jobs.flow.ScriptJobController`` y la exportación en ``jobs.export``. Los
diálogos de fichero se inyectan para poder probar la ventana sin QFileDialog.
Los botones llevan ``objectName`` estable, que es el contrato que usan los
tests y el teclado.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from genesis_video_ai.analysis.ffprobe import DEFAULT_MAX_FILE_BYTES, DEFAULT_RUNNER, FFProbeRunner
from genesis_video_ai.editorial.segments import validate_time_range
from genesis_video_ai.gemini.port import GeminiScriptPort, ScriptProposal
from genesis_video_ai.jobs.export import export_proposal_json, export_proposal_markdown
from genesis_video_ai.jobs.flow import JobEvent, JobResult, ScriptJobController
from genesis_video_ai.models.contracts import Segment, SourceMedia
from genesis_video_ai.ui.workers import ScriptJobWorker

PortFactory = Callable[[threading.Event], GeminiScriptPort]
VideoChooser = Callable[[], Path | None]
ExportChooser = Callable[[str, str], Path | None]
ExportWriter = Callable[[Path], Path]

GOOGLE_WARNING: str = (
    "Atención: al solicitar el guion, el vídeo original se envía a Google (Gemini API). "
    "Se aplican las condiciones del servicio configurado; el presupuesto objetivo es 0 €."
)

_PHASE_LABELS: dict[str, str] = {
    "analyzing": "Analizando el vídeo…",
    "validating": "Validando la selección de segmentos…",
    "generating": "Generando el guion (el material se envía a Google Gemini)…",
}

_SIN_ORIGINAL_ANALIZADO: str = "Sin original analizado"


class ScriptStudioWindow(QMainWindow):
    """Ventana del estudio: elegir vídeo, revisar segmentos y exportar guion."""

    job_event_ready = Signal(object)

    def __init__(
        self,
        port_factory: PortFactory,
        *,
        probe_runner: FFProbeRunner = DEFAULT_RUNNER,
        max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
        tolerance_s: float = 0.05,
        video_chooser: VideoChooser | None = None,
        export_chooser: ExportChooser | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """Construye la ventana; no analiza ni contacta con nada por su cuenta."""
        super().__init__(parent)
        self.setWindowTitle("GENESIS Video AI — Gemini Edition")
        self._port_factory = port_factory
        self._probe_runner = probe_runner
        self._max_file_bytes = max_file_bytes
        self._tolerance_s = tolerance_s
        self._video_chooser = video_chooser or _dialog_video_chooser
        self._export_chooser = export_chooser or _dialog_export_chooser
        self._source: SourceMedia | None = None
        self._segments: list[Segment] = []
        self._proposal: ScriptProposal | None = None
        self._worker: ScriptJobWorker | None = None
        self._active_controller: ScriptJobController | None = None
        self._build_ui()
        self.job_event_ready.connect(self._show_job_event)
        self._refresh_enabled()

    # -- construcción de la interfaz -------------------------------------

    def _build_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        fila_video = QHBoxLayout()
        self._video_path_edit = QLineEdit()
        self._video_path_edit.setObjectName("video-path-edit")
        self._video_path_edit.setReadOnly(True)
        self._video_path_edit.setPlaceholderText("Ningún vídeo seleccionado (MOV/MP4)")
        self._choose_button = QPushButton("Elegir vídeo (MOV/MP4)…")
        self._choose_button.setObjectName("choose-video")
        self._analyze_button = QPushButton("Analizar vídeo")
        self._analyze_button.setObjectName("analyze")
        fila_video.addWidget(self._video_path_edit, stretch=1)
        fila_video.addWidget(self._choose_button)
        fila_video.addWidget(self._analyze_button)
        root.addLayout(fila_video)

        self._source_info = QLabel(_SIN_ORIGINAL_ANALIZADO)
        self._source_info.setObjectName("source-info")
        root.addWidget(self._source_info)

        fila_parametros = QHBoxLayout()
        fila_parametros.addWidget(QLabel("Duración pedida"))
        self._duration_spin = QDoubleSpinBox()
        self._duration_spin.setObjectName("duration")
        self._duration_spin.setRange(1.0, 3600.0)
        self._duration_spin.setDecimals(1)
        self._duration_spin.setSingleStep(5.0)
        self._duration_spin.setValue(60.0)
        self._duration_spin.setSuffix(" s")
        fila_parametros.addWidget(self._duration_spin)
        fila_parametros.addWidget(QLabel("Inicio (s)"))
        self._segment_start_spin = QDoubleSpinBox()
        self._segment_start_spin.setObjectName("segment-start")
        self._segment_start_spin.setRange(0.0, 36000.0)
        self._segment_start_spin.setDecimals(2)
        fila_parametros.addWidget(self._segment_start_spin)
        fila_parametros.addWidget(QLabel("Fin (s)"))
        self._segment_end_spin = QDoubleSpinBox()
        self._segment_end_spin.setObjectName("segment-end")
        self._segment_end_spin.setRange(0.0, 36000.0)
        self._segment_end_spin.setDecimals(2)
        fila_parametros.addWidget(self._segment_end_spin)
        self._add_segment_button = QPushButton("Añadir segmento")
        self._add_segment_button.setObjectName("add-segment")
        self._remove_segment_button = QPushButton("Quitar seleccionado")
        self._remove_segment_button.setObjectName("remove-segment")
        fila_parametros.addWidget(self._add_segment_button)
        fila_parametros.addWidget(self._remove_segment_button)
        root.addLayout(fila_parametros)

        self._segments_table = QTableWidget(0, 3)
        self._segments_table.setObjectName("segments-table")
        self._segments_table.setHorizontalHeaderLabels(
            ["Entrada (s)", "Salida (s)", "Duración (s)"],
        )
        self._segments_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        root.addWidget(self._segments_table)

        self._request_button = QPushButton("Solicitar guion")
        self._request_button.setObjectName("request")
        root.addWidget(self._request_button)

        self._google_warning = QLabel(GOOGLE_WARNING)
        self._google_warning.setObjectName("google-warning")
        self._google_warning.setWordWrap(True)
        root.addWidget(self._google_warning)

        self._review_view = QPlainTextEdit()
        self._review_view.setObjectName("review")
        self._review_view.setReadOnly(True)
        self._review_view.setPlaceholderText("Aquí aparecerá el guion propuesto para revisión.")
        root.addWidget(self._review_view, stretch=1)

        fila_export = QHBoxLayout()
        self._export_json_button = QPushButton("Exportar JSON")
        self._export_json_button.setObjectName("export-json")
        self._export_markdown_button = QPushButton("Exportar Markdown")
        self._export_markdown_button.setObjectName("export-markdown")
        fila_export.addWidget(self._export_json_button)
        fila_export.addWidget(self._export_markdown_button)
        fila_export.addStretch(1)
        self._cancel_button = QPushButton("Cancelar trabajo")
        self._cancel_button.setObjectName("cancel")
        fila_export.addWidget(self._cancel_button)
        root.addLayout(fila_export)

        self._choose_button.clicked.connect(self.choose_video)
        self._analyze_button.clicked.connect(self.analyze_video)
        self._add_segment_button.clicked.connect(self.add_segment)
        self._remove_segment_button.clicked.connect(self.remove_selected_segment)
        self._request_button.clicked.connect(self.request_script)
        self._export_json_button.clicked.connect(self.export_json)
        self._export_markdown_button.clicked.connect(self.export_markdown)
        self._cancel_button.clicked.connect(self.cancel_job)

    # -- acciones públicas (las usan los botones y los tests) -------------

    def choose_video(self) -> None:
        """Abre el diálogo de vídeo y anota la ruta elegida."""
        if self.is_busy:
            return
        elegido = self._video_chooser()
        if elegido is None:
            self._show_status("No se eligió ningún vídeo")
            return
        cambio = str(elegido) != self._video_path_edit.text()
        self._video_path_edit.setText(str(elegido))
        if cambio:
            self._descartar_analisis()
        self._show_status(f"Vídeo seleccionado: {elegido}")
        self._refresh_enabled()

    def _descartar_analisis(self) -> None:
        """Otro vídeo seleccionado: el análisis, segmentos y guion previos ya no valen."""
        self._source = None
        self._segments = []
        self._proposal = None
        self._refresh_segments_table()
        self._review_view.clear()
        self._source_info.setText(_SIN_ORIGINAL_ANALIZADO)

    def analyze_video(self) -> None:
        """Lanza el análisis del vídeo seleccionado."""
        if self.is_busy:
            return
        ruta = self._video_path_edit.text().strip()
        if not ruta:
            self._show_status("Elige primero un vídeo MOV o MP4")
            return
        self._start_job(lambda controller: controller.analyze(Path(ruta)))

    def add_segment(self) -> None:
        """Valida la ventana pedida contra el original y la añade a la tabla."""
        if self._source is None:
            self._show_status("Analiza primero el vídeo")
            return
        inicio = self._segment_start_spin.value()
        fin = self._segment_end_spin.value()
        try:
            validate_time_range(inicio, fin, media_duration_s=self._source.duration_s)
        except ValueError as exc:
            self._show_status(f"Segmento rechazado: {exc}")
            return
        self._segments.append(Segment(source_id=self._source.id, start_s=inicio, end_s=fin))
        self._refresh_segments_table()
        self._show_status(f"Segmento añadido: [{_s(inicio)}, {_s(fin)}]")
        self._refresh_enabled()

    def remove_selected_segment(self) -> None:
        """Quita el segmento seleccionado en la tabla."""
        fila = self._segments_table.currentRow()
        if fila < 0 or fila >= len(self._segments):
            self._show_status("Selecciona un segmento en la tabla")
            return
        del self._segments[fila]
        self._refresh_segments_table()
        self._show_status("Segmento eliminado")
        self._refresh_enabled()

    def request_script(self) -> None:
        """Valida la selección y pide el guion al puerto configurado."""
        if self.is_busy:
            return
        if self._source is None or not self._segments:
            self._show_status("Analiza el vídeo y añade al menos un segmento")
            return
        duracion = self._duration_spin.value()
        segmentos = tuple(self._segments)
        fuente = self._source
        self._start_job(lambda controller: controller.generate(fuente, segmentos, duracion))

    def export_json(self) -> None:
        """Exporta el guion propuesto a JSON en la ruta elegida."""

        def escribir(destino: Path) -> Path:
            assert self._proposal is not None
            return export_proposal_json(self._proposal, self._fuente_para_exportar(), destino)

        self._export(escribir, "Exportar guion JSON", "Guion JSON (*.json)")

    def export_markdown(self) -> None:
        """Exporta el guion propuesto a Markdown en la ruta elegida."""

        def escribir(destino: Path) -> Path:
            assert self._proposal is not None
            return export_proposal_markdown(self._proposal, self._fuente_para_exportar(), destino)

        self._export(escribir, "Exportar guion Markdown", "Guion Markdown (*.md)")

    def cancel_job(self) -> None:
        """Solicita la parada del trabajo en marcha."""
        if self._active_controller is None:
            self._show_status("No hay trabajo en marcha")
            return
        self._active_controller.cancel()
        self._show_status("Cancelando el trabajo…")

    # -- estado observable -------------------------------------------------

    @property
    def is_busy(self) -> bool:
        """True mientras haya un trabajo en marcha."""
        return self._worker is not None

    @property
    def current_source(self) -> SourceMedia | None:
        """El original medido por el último análisis completado."""
        return self._source

    @property
    def current_proposal(self) -> ScriptProposal | None:
        """La propuesta de guion de la última generación completada."""
        return self._proposal

    @property
    def segment_values(self) -> tuple[tuple[float, float], ...]:
        """Las ventanas in/out de la tabla, en orden de inserción."""
        return tuple((segmento.start_s, segmento.end_s) for segmento in self._segments)

    @property
    def status_text(self) -> str:
        """El último mensaje mostrado en la barra de estado."""
        return self.statusBar().currentMessage()

    @property
    def review_text(self) -> str:
        """El texto de revisión del guion."""
        return self._review_view.toPlainText()

    # -- trabajos -----------------------------------------------------------

    def _start_job(self, job: Callable[[ScriptJobController], JobResult]) -> None:
        cancelacion = threading.Event()
        controller = ScriptJobController(
            self._port_factory(cancelacion),
            cancel_event=cancelacion,
            probe_runner=self._probe_runner,
            max_file_bytes=self._max_file_bytes,
            tolerance_s=self._tolerance_s,
            on_event=self.job_event_ready.emit,
        )
        self._active_controller = controller
        self._worker = ScriptJobWorker(lambda: job(controller))
        self._worker.job_finished.connect(self._on_job_finished)
        self._worker.start()
        self._show_status("Trabajo en marcha…")
        self._refresh_enabled()

    def _on_job_finished(self, result: JobResult) -> None:
        worker = self._worker
        self._worker = None
        self._active_controller = None
        if worker is not None:
            worker.deleteLater()
        if result.source is not None:
            self._source = result.source
            self._proposal = None
            self._segments = []
            self._refresh_segments_table()
            self._review_view.clear()
            self._source_info.setText(
                f"Original: {result.source.path.name} — "
                f"{_s(result.source.duration_s)} s reales ({result.source.container}, "
                f"{len(result.source.streams)} pistas)",
            )
            self._show_status(
                f"Original medido: {_s(result.source.duration_s)} s ({result.source.container})",
            )
        elif result.proposal is not None:
            self._proposal = result.proposal
            self._review_view.setPlainText(_review_text(self._proposal, self._source))
            self._show_status(
                f"Guion listo: {len(self._proposal.entries)} tramos "
                f"({_s(self._proposal.total_duration_s)} s)",
            )
        elif result.outcome == "cancelled":
            self._show_status("Trabajo cancelado")
        else:
            self._show_status(f"Error: {result.error}")
        self._refresh_enabled()

    def _fuente_para_exportar(self) -> SourceMedia:
        """El original sobre el que se construyó el guion actual."""
        if self._source is None:
            msg = "No hay original analizado del que exportar"
            raise ValueError(msg)
        return self._source

    def _export(self, writer: ExportWriter, title: str, file_filter: str) -> None:
        if self._proposal is None or self._source is None:
            self._show_status("Aún no hay guion que exportar: solicita primero el guion")
            return
        destino = self._export_chooser(title, file_filter)
        if destino is None:
            return
        try:
            ruta = writer(destino)
        except Exception as exc:
            self._show_status(f"No se pudo exportar: {exc}")
            return
        self._show_status(f"Guion exportado: {ruta}")

    # -- estado de la interfaz ----------------------------------------------

    def _refresh_enabled(self) -> None:
        ocupado = self.is_busy
        hay_ruta = bool(self._video_path_edit.text().strip())
        tiene_fuente = self._source is not None
        hay_segmentos = bool(self._segments)
        tiene_guion = self._proposal is not None
        self._choose_button.setEnabled(not ocupado)
        self._analyze_button.setEnabled(not ocupado and hay_ruta)
        self._duration_spin.setEnabled(not ocupado)
        self._segment_start_spin.setEnabled(not ocupado and tiene_fuente)
        self._segment_end_spin.setEnabled(not ocupado and tiene_fuente)
        self._add_segment_button.setEnabled(not ocupado and tiene_fuente)
        self._remove_segment_button.setEnabled(not ocupado and tiene_fuente and hay_segmentos)
        self._request_button.setEnabled(not ocupado and tiene_fuente and hay_segmentos)
        self._export_json_button.setEnabled(not ocupado and tiene_guion)
        self._export_markdown_button.setEnabled(not ocupado and tiene_guion)
        self._cancel_button.setEnabled(ocupado)

    def _refresh_segments_table(self) -> None:
        self._segments_table.setRowCount(len(self._segments))
        for fila, segmento in enumerate(self._segments):
            valores = (f"{segmento.start_s:g}", f"{segmento.end_s:g}", f"{segmento.duration_s:g}")
            for columna, valor in enumerate(valores):
                self._segments_table.setItem(fila, columna, QTableWidgetItem(valor))

    def _show_job_event(self, event: JobEvent) -> None:
        mensaje = event.message or _PHASE_LABELS.get(event.phase, event.phase)
        if event.phase in _PHASE_LABELS:
            mensaje = _PHASE_LABELS[event.phase]
        self._show_status(mensaje)

    def _show_status(self, mensaje: str) -> None:
        self.statusBar().showMessage(mensaje)


def _dialog_video_chooser() -> Path | None:
    ruta, _ = QFileDialog.getOpenFileName(
        None,
        "Elegir vídeo (MOV/MP4)",
        "",
        "Vídeo (MOV/MP4) (*.mov *.mp4)",
    )
    return Path(ruta) if ruta else None


def _dialog_export_chooser(title: str, file_filter: str) -> Path | None:
    ruta, _ = QFileDialog.getSaveFileName(None, title, "", file_filter)
    return Path(ruta) if ruta else None


def _review_text(proposal: ScriptProposal, source: SourceMedia | None) -> str:
    lineas = [
        f"Guion propuesto: {len(proposal.entries)} tramos — duración total "
        f"{_s(proposal.total_duration_s)} s",
    ]
    if source is not None:
        lineas.append(
            f"Original: {source.path} ({source.container}, {_s(source.duration_s)} s reales)",
        )
    lineas.append("")
    for numero, entrada in enumerate(proposal.entries, 1):
        lineas.append(f"{numero}. [{_s(entrada.start_s)} → {_s(entrada.end_s)} s]")
        lineas.append(f"   Narración: {entrada.narration}")
        if entrada.justification:
            lineas.append(f"   Justificación: {entrada.justification}")
    return "\n".join(lineas)


def _s(valor: float) -> str:
    return f"{valor:g}"
