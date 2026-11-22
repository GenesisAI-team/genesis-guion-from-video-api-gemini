"""Conftest de unitarios: Qt en modo offscreen para los tests de UI (GEN-50).

La variable de entorno se fija antes de que pytest importe cualquier módulo
de la UI, de modo que QApplication nunca pide pantalla; los tests siguen
siendo deterministas en CI y en local.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """Una única QApplication de sesión para todos los tests de UI."""
    app = QApplication.instance() or QApplication([])
    yield app
