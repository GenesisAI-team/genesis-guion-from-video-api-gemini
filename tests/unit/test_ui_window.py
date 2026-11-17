"""Ventana principal PySide6: flujo vídeo → guion → exportación (GEN-50).

Los diálogos nativos se inyectan: los tests no abren QFileDialog. Los botones
se localizan por ``objectName`` (contrato público) y las aserciones usan las
propiedades públicas de la ventana.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Sequence
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any

import pytest
from helpers import PuertoEcoScript
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QTableWidget,
)
from ui_helpers import boton, esperar_hasta

from genesis_video_ai.gemini.port import ScriptedGeminiScriptPort
from genesis_video_ai.ui.window import GOOGLE_WARNING, ScriptStudioWindow

PROBE_PAYLOAD: dict[str, Any] = {
    "streams": [
        {"index": 0, "codec_type": "video", "codec_name": "h264", "width": 1280, "height": 720},
        {"index": 1, "codec_type": "audio", "codec_name": "aac"},
    ],
    "format": {"duration": "120.0", "format_name": "mov,mp4,m4a,3gp,3g2,mj2"},
}


def runner_de_prueba(args: Sequence[str]) -> CompletedProcess[str]:
    return CompletedProcess(
        args=list(args),
        returncode=0,
        stdout=json.dumps(PROBE_PAYLOAD),
        stderr="",
    )


@pytest.fixture()
def original(tmp_path: Path) -> Path:
    ruta = tmp_path / "original.mp4"
    ruta.write_bytes(b"x")
    return ruta


def ventanita(
    original: Path,
    *,
    puerto: Any | None = None,
    probe_runner: Any = None,
    export_destinos: Sequence[Path | None] = (),
    export_capturas: list[tuple[str, str]] | None = None,
    **ajustes: Any,
) -> ScriptStudioWindow:
    """Ventana con fakes: puerto eco y diálogos inyectados."""
    puerto_resuelto = puerto if puerto is not None else PuertoEcoScript()
    destinos = iter(export_destinos)

    def elegir_export(titulo: str, filtro: str) -> Path | None:
        if export_capturas is not None:
            export_capturas.append((titulo, filtro))
        return next(destinos, None)

    return ScriptStudioWindow(
        lambda cancel_event: puerto_resuelto,
        probe_runner=probe_runner if probe_runner is not None else runner_de_prueba,
        video_chooser=lambda: original,
        export_chooser=elegir_export,
        **ajustes,
    )


def analizar_original(ventana: ScriptStudioWindow, qapp: Any) -> None:
    boton(ventana, "analyze").click()
    esperar_hasta(qapp, lambda: not ventana.is_busy)


def campo(ventana: ScriptStudioWindow, nombre: str) -> QDoubleSpinBox:
    encontrado = ventana.findChild(QDoubleSpinBox, nombre)
    if encontrado is None:
        msg = f"No existe el campo {nombre!r}"
        raise AssertionError(msg)
    return encontrado


def anadir_segmento(ventana: ScriptStudioWindow, inicio: float, fin: float) -> None:
    campo(ventana, "segment-start").setValue(inicio)
    campo(ventana, "segment-end").setValue(fin)
    boton(ventana, "add-segment").click()


class TestFlujoCompleto:
    def test_del_video_al_guion_y_a_la_exportacion(
        self,
        qapp: Any,
        tmp_path: Path,
        original: Path,
    ) -> None:
        destino_json = tmp_path / "salidas" / "guion.json"
        destino_md = tmp_path / "salidas" / "guion.md"
        capturas: list[tuple[str, str]] = []
        ventana = ventanita(
            original,
            export_destinos=[destino_json, destino_md],
            export_capturas=capturas,
        )

        boton(ventana, "choose-video").click()
        assert ventana.findChild(QLineEdit, "video-path-edit").text() == str(original)

        analizar_original(ventana, qapp)
        assert ventana.current_source is not None
        assert "120" in ventana.findChild(QLabel, "source-info").text()
        assert "mp4" in ventana.findChild(QLabel, "source-info").text()

        anadir_segmento(ventana, 0.0, 45.0)
        anadir_segmento(ventana, 60.0, 105.0)
        assert ventana.segment_values == ((0.0, 45.0), (60.0, 105.0))
        assert ventana.findChild(QTableWidget, "segments-table").rowCount() == 2

        campo(ventana, "duration").setValue(90.0)
        boton(ventana, "request").click()
        esperar_hasta(qapp, lambda: not ventana.is_busy)

        guion = ventana.current_proposal
        assert guion is not None
        assert guion.total_duration_s == pytest.approx(90.0)
        revision = ventana.findChild(QPlainTextEdit, "review").toPlainText()
        assert "Guion propuesto" in revision
        assert "90" in revision
        assert str(original.resolve()) in revision
        assert "Narración sobre [0, 45] s." in revision
        assert "Justificación: Derivado del material medido" in revision

        boton(ventana, "export-json").click()
        boton(ventana, "export-markdown").click()
        esperar_hasta(qapp, lambda: "Guion exportado" in ventana.status_text)

        assert destino_json.exists()
        contenido = json.loads(destino_json.read_text(encoding="utf-8"))
        assert contenido["source"]["path"] == str(original.resolve())
        assert contenido["entries"][1]["start_s"] == pytest.approx(60.0)
        assert destino_md.exists()
        assert "| 2 | 60 | 105 | 45 |" in destino_md.read_text(encoding="utf-8")
        assert capturas[0] == ("Exportar guion JSON", "Guion JSON (*.json)")
        assert capturas[1][0] == "Exportar guion Markdown"

    def test_advertencia_de_envio_a_google_visible(self, original: Path) -> None:
        ventana = ventanita(original)

        aviso = ventana.findChild(QLabel, "google-warning").text()
        assert aviso == GOOGLE_WARNING
        assert "Google" in aviso
        assert "Gemini" in aviso


class TestErroresDeLaVentana:
    def test_analizar_un_original_inexistente_avisa(self, qapp: Any, tmp_path: Path) -> None:
        ventana = ventanita(tmp_path / "ausente.mp4")

        boton(ventana, "choose-video").click()
        analizar_original(ventana, qapp)

        assert ventana.current_source is None
        assert "no existe" in ventana.status_text

    def test_segmento_fuera_de_la_duracion_real_rechazado(
        self,
        qapp: Any,
        original: Path,
    ) -> None:
        ventana = ventanita(original)
        boton(ventana, "choose-video").click()
        analizar_original(ventana, qapp)

        anadir_segmento(ventana, 0.0, 200.0)

        assert ventana.segment_values == ()
        assert "Segmento rechazado" in ventana.status_text

    def test_segmento_sin_analisis_previo_rechazado(self, original: Path) -> None:
        ventana = ventanita(original)

        ventana.add_segment()

        assert ventana.segment_values == ()
        assert "Analiza primero" in ventana.status_text

    def test_solicitar_guion_sin_segmentos_avisa(self, original: Path) -> None:
        ventana = ventanita(original)

        ventana.request_script()

        assert ventana.status_text == "Analiza el vídeo y añade al menos un segmento"

    def test_elegir_video_y_cancelar_el_dialogo(self, original: Path) -> None:
        puerto = ScriptedGeminiScriptPort(responses=[])
        ventana = ScriptStudioWindow(
            lambda cancel_event: puerto,
            probe_runner=runner_de_prueba,
            video_chooser=lambda: None,
        )

        boton(ventana, "choose-video").click()

        assert ventana.findChild(QLineEdit, "video-path-edit").text() == ""
        assert "No se eligió ningún vídeo" in ventana.status_text

    def test_exportar_sin_guion_avisa(self, original: Path, tmp_path: Path) -> None:
        ventana = ventanita(original)

        ventana.export_json()

        assert "Aún no hay guion que exportar" in ventana.status_text
        assert not (tmp_path / "guion.json").exists()

    def test_exportar_y_cancelar_el_dialogo_no_escribe(
        self,
        qapp: Any,
        tmp_path: Path,
        original: Path,
    ) -> None:
        ventana = ventanita(original, export_destinos=[None])
        boton(ventana, "choose-video").click()
        analizar_original(ventana, qapp)
        anadir_segmento(ventana, 0.0, 90.0)
        campo(ventana, "duration").setValue(90.0)
        boton(ventana, "request").click()
        esperar_hasta(qapp, lambda: not ventana.is_busy)

        boton(ventana, "export-json").click()

        assert ventana.current_proposal is not None
        assert not any(ruta.name.startswith("guion") for ruta in tmp_path.iterdir())

    def test_exportar_a_un_destino_invalido_avisa(
        self,
        qapp: Any,
        tmp_path: Path,
        original: Path,
    ) -> None:
        ventana = ventanita(original, export_destinos=[tmp_path])
        boton(ventana, "choose-video").click()
        analizar_original(ventana, qapp)
        anadir_segmento(ventana, 0.0, 90.0)
        campo(ventana, "duration").setValue(90.0)
        boton(ventana, "request").click()
        esperar_hasta(qapp, lambda: not ventana.is_busy)

        boton(ventana, "export-json").click()

        assert "No se pudo exportar" in ventana.status_text


class TestCancelacion:
    def test_cancelar_notifica_al_puerto_con_el_mismo_evento(
        self,
        qapp: Any,
        original: Path,
    ) -> None:
        eventos_del_puerto: list[threading.Event] = []

        def fabrica(evento: threading.Event) -> Any:
            eventos_del_puerto.append(evento)
            return PuertoEcoScript(pausa_s=0.3)

        ventana = ScriptStudioWindow(
            fabrica,
            probe_runner=runner_de_prueba,
            video_chooser=lambda: original,
        )
        boton(ventana, "choose-video").click()
        analizar_original(ventana, qapp)
        anadir_segmento(ventana, 0.0, 90.0)
        campo(ventana, "duration").setValue(90.0)

        boton(ventana, "request").click()
        esperar_hasta(qapp, lambda: ventana.is_busy)
        boton(ventana, "cancel").click()
        esperar_hasta(qapp, lambda: not ventana.is_busy, timeout_s=15.0)

        assert eventos_del_puerto
        assert eventos_del_puerto[-1].is_set()
        assert "cancelado" in ventana.status_text.lower()

    def test_cancelar_mientras_genera_deja_el_guion_pendiente(
        self,
        qapp: Any,
        original: Path,
    ) -> None:
        ventana = ventanita(original, puerto=PuertoEcoScript(pausa_s=0.3))
        boton(ventana, "choose-video").click()
        analizar_original(ventana, qapp)
        anadir_segmento(ventana, 0.0, 90.0)

        boton(ventana, "request").click()
        esperar_hasta(qapp, lambda: ventana.is_busy)
        boton(ventana, "cancel").click()
        esperar_hasta(qapp, lambda: not ventana.is_busy, timeout_s=15.0)

        assert ventana.current_proposal is None
        assert "cancelado" in ventana.status_text.lower()

    def test_cancelar_sin_trabajo_en_marcha_avisa(self, original: Path) -> None:
        ventana = ventanita(original)

        ventana.cancel_job()

        assert "No hay trabajo en marcha" in ventana.status_text


class TestCambioDeVideo:
    """Otro vídeo seleccionado invalida el análisis, los segmentos y el guion previos."""

    def test_elegir_otro_video_invalida_el_analisis_anterior(
        self,
        qapp: Any,
        tmp_path: Path,
        original: Path,
    ) -> None:
        otro = tmp_path / "otro.mp4"
        otro.write_bytes(b"x")
        elegido = {"ruta": original}
        puerto = PuertoEcoScript()
        ventana = ScriptStudioWindow(
            lambda cancel_event: puerto,
            probe_runner=runner_de_prueba,
            video_chooser=lambda: elegido["ruta"],
        )
        boton(ventana, "choose-video").click()
        analizar_original(ventana, qapp)
        anadir_segmento(ventana, 0.0, 90.0)
        campo(ventana, "duration").setValue(90.0)
        boton(ventana, "request").click()
        esperar_hasta(qapp, lambda: not ventana.is_busy)
        assert ventana.current_proposal is not None

        elegido["ruta"] = otro
        boton(ventana, "choose-video").click()

        assert ventana.current_source is None
        assert ventana.segment_values == ()
        assert ventana.current_proposal is None
        assert ventana.findChild(QPlainTextEdit, "review").toPlainText() == ""
        assert ventana.findChild(QLabel, "source-info").text() == "Sin original analizado"
        assert ventana.findChild(QTableWidget, "segments-table").rowCount() == 0
        assert boton(ventana, "request").isEnabled() is False
        assert boton(ventana, "export-json").isEnabled() is False
        assert boton(ventana, "export-markdown").isEnabled() is False

        solicitudes_antes = len(puerto.requests)
        ventana.request_script()

        assert ventana.is_busy is False
        assert len(puerto.requests) == solicitudes_antes
        assert "Analiza el vídeo" in ventana.status_text

    def test_tras_cambiar_de_video_un_nuevo_analisis_habilita_la_generacion(
        self,
        qapp: Any,
        tmp_path: Path,
        original: Path,
    ) -> None:
        otro = tmp_path / "otro.mp4"
        otro.write_bytes(b"x")
        elegido = {"ruta": original}
        puerto = PuertoEcoScript()
        ventana = ScriptStudioWindow(
            lambda cancel_event: puerto,
            probe_runner=runner_de_prueba,
            video_chooser=lambda: elegido["ruta"],
        )
        boton(ventana, "choose-video").click()
        analizar_original(ventana, qapp)
        anadir_segmento(ventana, 0.0, 90.0)

        elegido["ruta"] = otro
        boton(ventana, "choose-video").click()
        analizar_original(ventana, qapp)
        anadir_segmento(ventana, 0.0, 90.0)
        campo(ventana, "duration").setValue(90.0)
        boton(ventana, "request").click()
        esperar_hasta(qapp, lambda: not ventana.is_busy)

        guion = ventana.current_proposal
        assert guion is not None
        assert str(otro.resolve()) in ventana.review_text
        assert puerto.requests[-1].source.path == otro.resolve()


class TestProgresoYRecuperacion:
    def test_el_estado_muestra_las_fases_del_trabajo(self, qapp: Any, original: Path) -> None:
        def runner_lento(args: Sequence[str]) -> CompletedProcess[str]:
            time.sleep(0.25)
            return runner_de_prueba(args)

        ventana = ventanita(original, puerto=PuertoEcoScript(), probe_runner=runner_lento)

        boton(ventana, "choose-video").click()
        boton(ventana, "analyze").click()
        esperar_hasta(qapp, lambda: "Analizando" in ventana.status_text)
        esperar_hasta(qapp, lambda: not ventana.is_busy)

        assert ventana.current_source is not None

    def test_reanalizar_tras_un_error_recupera_el_flujo(self, qapp: Any, tmp_path: Path) -> None:
        elegido = {"ruta": tmp_path / "ausente.mp4"}
        puerto = ScriptedGeminiScriptPort(responses=[])
        ventana = ScriptStudioWindow(
            lambda cancel_event: puerto,
            probe_runner=runner_de_prueba,
            video_chooser=lambda: elegido["ruta"],
        )
        boton(ventana, "choose-video").click()
        analizar_original(ventana, qapp)
        assert ventana.current_source is None

        valido = tmp_path / "valido.mp4"
        valido.write_bytes(b"x")
        elegido["ruta"] = valido
        boton(ventana, "choose-video").click()
        analizar_original(ventana, qapp)

        assert ventana.current_source is not None


def test_los_botones_arrancan_en_su_estado_correcto(original: Path) -> None:
    ventana = ventanita(original)

    assert boton(ventana, "analyze").isEnabled() is False
    assert boton(ventana, "request").isEnabled() is False
    assert boton(ventana, "export-json").isEnabled() is False
    assert boton(ventana, "cancel").isEnabled() is False
    assert ventana.is_busy is False
    assert ventana.current_source is None
    assert ventana.current_proposal is None
    assert ventana.segment_values == ()
