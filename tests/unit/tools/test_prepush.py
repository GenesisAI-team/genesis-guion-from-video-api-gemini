"""Tests del orquestador pre-push."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from tools import prepush

POLICY = """
[thresholds]
core = 100.0
important = 80.0
infrastructure = 0.0

[files]
"src/pkg/core.py" = "core"
"""


def _fake_run(returncode: int, captured: dict[str, Any]) -> Any:
    def runner(args: list[str], *, check: bool) -> SimpleNamespace:
        captured["args"] = args
        captured["check"] = check
        return SimpleNamespace(returncode=returncode)

    return runner


def test_prepush_stops_when_tests_fail(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(subprocess, "run", _fake_run(3, captured))

    exit_code = prepush.main([])

    assert exit_code == 3
    assert sys.executable == captured["args"][0]
    assert "pytest" in captured["args"]
    assert "PRE-PUSH: la suite de tests ha fallado" in capsys.readouterr().err


def test_prepush_runs_coverage_gate_when_tests_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(subprocess, "run", _fake_run(0, {}))
    coverage_path = tmp_path / "coverage.json"
    coverage_path.write_text(
        json.dumps({"files": {"src/pkg/core.py": {"summary": {"percent_covered": 100.0}}}}),
        encoding="utf-8",
    )
    policy_path = tmp_path / "coverage-policy.toml"
    policy_path.write_text(POLICY, encoding="utf-8")

    exit_code = prepush.main(["--coverage-json", str(coverage_path), "--policy", str(policy_path)])

    assert exit_code == 0


def test_prepush_propagates_coverage_violation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(subprocess, "run", _fake_run(0, {}))
    coverage_path = tmp_path / "coverage.json"
    coverage_path.write_text(
        json.dumps({"files": {"src/pkg/core.py": {"summary": {"percent_covered": 50.0}}}}),
        encoding="utf-8",
    )
    policy_path = tmp_path / "coverage-policy.toml"
    policy_path.write_text(POLICY, encoding="utf-8")

    exit_code = prepush.main(["--coverage-json", str(coverage_path), "--policy", str(policy_path)])

    assert exit_code == 1
