"""Arranque de la aplicación de escritorio (GEN-50)."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from genesis_video_ai.ui.app import main
from genesis_video_ai.ui.window import ScriptStudioWindow


def test_main_arranca_la_ventana_y_sale(qapp: QApplication) -> None:
    vistas: list[bool] = []

    def corredor(app: QApplication) -> int:
        vistas.append(
            any(isinstance(widget, ScriptStudioWindow) for widget in app.topLevelWidgets()),
        )
        return 7

    codigo = main([], run_loop=corredor)

    assert codigo == 7
    assert vistas == [True]


def test_main_acepta_argv_de_la_linea_de_comandos(qapp: QApplication) -> None:
    codigo = main(["genesis-video-ai"], run_loop=lambda application: 0)

    assert codigo == 0
