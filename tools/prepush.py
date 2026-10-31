"""Orquestador del gate pre-push: suite completa + cobertura 100/80/0.

Encadena ambos pasos en un único proceso para que el gate de cobertura nunca
lea un informe obsoleto ni se ejecute en paralelo con los tests.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence
from typing import Final

from tools.check_coverage import main as check_coverage_main

PYTEST_ARGS: Final = (
    "-q",
    "--cov=genesis_video_ai",
    "--cov-report=json:coverage.json",
)


def main(argv: Sequence[str] | None = None) -> int:
    """Ejecuta la suite completa y aplica después el gate de cobertura."""
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", *PYTEST_ARGS],
        check=False,
    )
    if completed.returncode != 0:
        sys.stderr.write("PRE-PUSH: la suite de tests ha fallado; no se evalua cobertura.\n")
        return completed.returncode

    return check_coverage_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
