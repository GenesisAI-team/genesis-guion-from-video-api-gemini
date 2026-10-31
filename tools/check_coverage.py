"""Gate de cobertura 100/80/0 por archivo.

Uso:
    uv run pytest --cov=genesis_video_ai --cov-report=json:coverage.json
    uv run python tools/check_coverage.py
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

from tools.coverage_policy import DEFAULT_POLICY_PATH, CoveragePolicy, PolicyError

EXIT_OK: Final = 0
EXIT_VIOLATION: Final = 1
EXIT_ERROR: Final = 2
DEFAULT_COVERAGE_JSON: Final = Path("coverage.json")


def _measured_percentages(report: Any) -> dict[str, float]:
    """Extrae el porcentaje cubierto de cada archivo del informe de coverage.py."""
    files = report.get("files") if isinstance(report, dict) else None
    if not isinstance(files, dict) or not files:
        msg = "El informe de coverage no contiene archivos medidos"
        raise PolicyError(msg)

    measured: dict[str, float] = {}
    for path, entry in files.items():
        summary = entry.get("summary") if isinstance(entry, dict) else None
        if not isinstance(summary, dict) or "percent_covered" not in summary:
            msg = f"Entrada de coverage inválida para {path}"
            raise PolicyError(msg)
        measured[path] = float(summary["percent_covered"])
    return measured


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="check_coverage",
        description="Aplica la política de cobertura 100/80/0 por archivo.",
    )
    parser.add_argument(
        "--coverage-json",
        type=Path,
        default=DEFAULT_COVERAGE_JSON,
        help="Informe JSON generado por coverage.py (por defecto: coverage.json).",
    )
    parser.add_argument(
        "--policy",
        type=Path,
        default=DEFAULT_POLICY_PATH,
        help="Archivo de política de cobertura (por defecto: coverage-policy.toml).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Ejecuta el gate y devuelve el código de salida del proceso."""
    args = _build_parser().parse_args(argv)

    try:
        report = json.loads(args.coverage_json.read_text(encoding="utf-8"))
        policy = CoveragePolicy.load(args.policy)
        measured = _measured_percentages(report)
        violations = policy.evaluate(measured)
    except (OSError, json.JSONDecodeError, PolicyError) as exc:
        sys.stderr.write(f"GATE COBERTURA: error -> {exc}\n")
        return EXIT_ERROR

    sys.stdout.write(f"Archivos medidos: {len(measured)}\n")
    for path in sorted(measured):
        category = policy.category_for(path)
        threshold = policy.thresholds[category]
        sys.stdout.write(f"  {measured[path]:6.2f}%  min {threshold:6.2f}%  {category:15} {path}\n")

    if violations:
        sys.stdout.write("\nGATE COBERTURA: FALLO\n")
        for violation in violations:
            sys.stdout.write(f"  - {violation.describe()}\n")
        return EXIT_VIOLATION

    sys.stdout.write("\nGATE COBERTURA: OK\n")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
