"""Ayudas para los tests de la UI PySide6 (GEN-50): bombear eventos y localizar widgets."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest
from PySide6.QtWidgets import QPushButton, QWidget

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication


def esperar_hasta(
    app: QApplication,
    condicion: Callable[[], bool],
    *,
    timeout_s: float = 10.0,
) -> None:
    """Procesa eventos hasta que la condición se cumpla o se agote el plazo."""
    limite = time.monotonic() + timeout_s
    while time.monotonic() < limite:
        app.processEvents()
        if condicion():
            return
        time.sleep(0.005)
    pytest.fail("La condición no se alcanzó dentro del plazo")


def boton(ventana: QWidget, nombre: str) -> QPushButton:
    """Localiza un botón por su objectName (contrato público de la ventana)."""
    encontrado = ventana.findChild(QPushButton, nombre)
    if encontrado is None:
        msg = f"No existe el botón {nombre!r}"
        raise AssertionError(msg)
    return encontrado
