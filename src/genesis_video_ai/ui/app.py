"""Arranque de la aplicación GENESIS Video AI (GEN-50).

Monta la ventana con el puerto Gemini real configurado por entorno. Sin
credencial la aplicación abre igualmente: el fallo llega de forma controlada
al solicitar el guion, nunca de forma silenciosa y nunca sin opt-in.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence

from PySide6.QtWidgets import QApplication

from genesis_video_ai.gemini.client import RealGeminiScriptPort
from genesis_video_ai.gemini.config import GeminiClientConfig
from genesis_video_ai.gemini.port import GeminiScriptPort
from genesis_video_ai.ui.window import ScriptStudioWindow


def main(
    argv: Sequence[str] | None = None,
    *,
    run_loop: Callable[[QApplication], int] | None = None,
) -> int:
    """Arranca la aplicación de escritorio y devuelve el código de salida."""
    app = QApplication.instance() or QApplication(list(argv) if argv is not None else [])
    ventana = ScriptStudioWindow(real_port_factory)
    ventana.show()
    corredor = run_loop or _ejecutar_bucle
    return corredor(app)


def real_port_factory(cancel_event: threading.Event) -> GeminiScriptPort:
    """Puerto Gemini real, con su cancelación enlazada al trabajo en curso."""
    return RealGeminiScriptPort(
        GeminiClientConfig.from_env(),
        cancel_event=cancel_event,
    )


def _ejecutar_bucle(app: QApplication) -> int:
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
