"""Tests de la politica de cobertura 100/80/0 por archivo."""

from __future__ import annotations

from pathlib import Path

import pytest
from tools.coverage_policy import CoveragePolicy, PolicyError


def _write_policy(tmp_path: Path, body: str) -> Path:
    policy_path = tmp_path / "coverage-policy.toml"
    policy_path.write_text(body, encoding="utf-8")
    return policy_path


def _valid_policy_text() -> str:
    return """
[thresholds]
core = 100.0
important = 80.0
infrastructure = 0.0

[files]
"src/pkg/core.py" = "core"
"src/pkg/__init__.py" = "infrastructure"
"""


def test_classifies_files_by_first_matching_pattern(tmp_path: Path) -> None:
    policy = CoveragePolicy.load(_write_policy(tmp_path, _valid_policy_text()))

    assert policy.category_for("src/pkg/core.py") == "core"
    assert policy.category_for("src\\pkg\\core.py") == "core"
    assert policy.category_for("./src/pkg/__init__.py") == "infrastructure"


def test_unclassified_file_fails_closed(tmp_path: Path) -> None:
    policy = CoveragePolicy.load(_write_policy(tmp_path, _valid_policy_text()))

    with pytest.raises(PolicyError, match="sin clasificar"):
        policy.category_for("src/pkg/new_module.py")


def test_missing_policy_file_is_reported(tmp_path: Path) -> None:
    with pytest.raises(PolicyError, match="No existe"):
        CoveragePolicy.load(tmp_path / "no-existe.toml")


def test_empty_file_list_is_rejected(tmp_path: Path) -> None:
    body = """
[thresholds]
core = 100.0
"""
    with pytest.raises(PolicyError, match="al menos un archivo"):
        CoveragePolicy.load(_write_policy(tmp_path, body))


def test_unknown_category_in_policy_is_rejected(tmp_path: Path) -> None:
    body = """
[thresholds]
core = 100.0

[files]
"src/pkg/core.py" = "critico"
"""
    with pytest.raises(PolicyError, match="critico"):
        CoveragePolicy.load(_write_policy(tmp_path, body))


def test_missing_threshold_for_category_is_rejected(tmp_path: Path) -> None:
    body = """
[thresholds]
core = 100.0

[files]
"src/pkg/core.py" = "important"
"""
    with pytest.raises(PolicyError, match="important"):
        CoveragePolicy.load(_write_policy(tmp_path, body))


def test_evaluate_flags_coverage_below_threshold(tmp_path: Path) -> None:
    policy = CoveragePolicy.load(_write_policy(tmp_path, _valid_policy_text()))

    violations = policy.evaluate({"src/pkg/core.py": 99.99})

    assert len(violations) == 1
    assert violations[0].category == "core"
    assert violations[0].threshold == 100.0
    assert "99.99%" in violations[0].describe()


def test_evaluate_allows_coverage_at_threshold(tmp_path: Path) -> None:
    policy = CoveragePolicy.load(_write_policy(tmp_path, _valid_policy_text()))

    assert policy.evaluate({"src/pkg/core.py": 100.0}) == ()


def test_infrastructure_has_no_minimum(tmp_path: Path) -> None:
    policy = CoveragePolicy.load(_write_policy(tmp_path, _valid_policy_text()))

    assert policy.evaluate({"src/pkg/__init__.py": 0.0}) == ()
