"""Temporales de sesión del análisis (GEN-36).

Reglas de producto: nada se almacena permanentemente y los originales nunca
se tocan. Todo material derivado vive en un directorio temporal de sesión
que se elimina al finalizar el flujo, incluso si falla.
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Final

SESSION_TEMP_PREFIX: Final = "genesis-video-ai-"


@contextmanager
def session_temp_dir(
    prefix: str | None = None,
    root: Path | str | None = None,
) -> Iterator[Path]:
    """Crea un directorio temporal de sesión y lo elimina al salir.

    Args:
        prefix: Prefijo del directorio (por defecto el del proyecto).
        root: Directorio raíz para crearlo (por defecto el TMP del sistema,
            útil en tests).

    Yields:
        La ruta del directorio, existente durante la sesión.
    """
    path = Path(
        tempfile.mkdtemp(
            prefix=prefix if prefix is not None else SESSION_TEMP_PREFIX,
            dir=str(root) if root is not None else None,
        ),
    )
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
