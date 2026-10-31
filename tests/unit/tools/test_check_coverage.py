"""Tests del CLI del gate de cobertura."""

from __future__ import annotations

import json
from pathlib import Path

from tools.check_coverage import main

POLICY = """
[thresholds]
core = 100.0
important = 80.0
infrastructure = 0.0

[files]
"src/pkg/core.py" = "core"
"src/pkg/support.py" = "important"
"src/pkg/__init__.py" = "infrastructure"
"""


def _prepare(tmp_path: Path, percentages: dict[str, float]) -> tuple[Path, Path]:
    policy_path = tmp_path / "coverage-policy.toml"
    policy_path.write_text(POLICY, encoding="utf-8")
    report = {
        "files": {
            path: {"summary": {"percent_covered": value, "num_statements": 10}}
            for path, value in percentages.items()
        }
    }
    coverage_path = tmp_path / "coverage.json"
    coverage_path.write_text(json.dumps(report), encoding="utf-8")
    return coverage_path, policy_path


def test_main_passes_when_every_file_meets_its_threshold(tmp_path: Path, capsys: object) -> None:
    coverage_path, policy_path = _prepare(
        tmp_path,
        {
            "src/pkg/core.py": 100.0,
            "src/pkg/support.py": 82.5,
            "src/pkg/__init__.py": 0.0,
        },
    )

    exit_code = main(["--coverage-json", str(coverage_path), "--policy", str(policy_path)])

    assert exit_code == 0
    assert "GATE COBERTURA: OK" in capsys.readouterr().out


def test_main_fails_when_core_is_below_one_hundred(tmp_path: Path, capsys: object) -> None:
    coverage_path, policy_path = _prepare(tmp_path, {"src/pkg/core.py": 97.0})

    exit_code = main(["--coverage-json", str(coverage_path), "--policy", str(policy_path)])

    assert exit_code == 1
    output = capsys.readouterr().out
    assert "GATE COBERTURA: FALLO" in output
    assert "src/pkg/core.py" in output


def test_main_fails_when_a_file_is_not_classified(tmp_path: Path, capsys: object) -> None:
    coverage_path, policy_path = _prepare(tmp_path, {"src/pkg/unknown.py": 100.0})

    exit_code = main(["--coverage-json", str(coverage_path), "--policy", str(policy_path)])

    assert exit_code == 2
    assert "sin clasificar" in capsys.readouterr().err


def test_main_reports_missing_coverage_report(tmp_path: Path, capsys: object) -> None:
    policy_path = tmp_path / "coverage-policy.toml"
    policy_path.write_text(POLICY, encoding="utf-8")

    exit_code = main(
        [
            "--coverage-json",
            str(tmp_path / "no-existe.json"),
            "--policy",
            str(policy_path),
        ]
    )

    assert exit_code == 2
    assert "GATE COBERTURA: error" in capsys.readouterr().err


def test_main_rejects_report_without_measured_files(tmp_path: Path, capsys: object) -> None:
    coverage_path, policy_path = _prepare(tmp_path, {})
    coverage_path.write_text(json.dumps({"files": {}}), encoding="utf-8")

    exit_code = main(["--coverage-json", str(coverage_path), "--policy", str(policy_path)])

    assert exit_code == 2
    assert "no contiene archivos" in capsys.readouterr().err
