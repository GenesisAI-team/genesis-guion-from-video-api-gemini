"""Tests CORE del validador de rangos temporales (GEN-13 §6)."""

from __future__ import annotations

import math

import pytest

from genesis_video_ai.editorial.segments import TimeRange, validate_time_range


def test_valid_range_returns_time_range_with_real_duration() -> None:
    result = validate_time_range(10.0, 42.5, media_duration_s=60.0)

    assert result == TimeRange(start_s=10.0, end_s=42.5)
    assert result.duration_s == pytest.approx(32.5)


def test_range_covering_whole_media_is_allowed() -> None:
    result = validate_time_range(0.0, 60.0, media_duration_s=60.0)

    assert result.duration_s == pytest.approx(60.0)


@pytest.mark.parametrize("start_s", [-0.01, -5.0])
def test_negative_start_is_rejected(start_s: float) -> None:
    with pytest.raises(ValueError, match="start_s"):
        validate_time_range(start_s, 10.0, media_duration_s=60.0)


@pytest.mark.parametrize(("start_s", "end_s"), [(5.0, 5.0), (5.0, 4.0)])
def test_empty_or_inverted_range_is_rejected(start_s: float, end_s: float) -> None:
    with pytest.raises(ValueError, match="end_s"):
        validate_time_range(start_s, end_s, media_duration_s=60.0)


def test_end_beyond_media_duration_is_rejected() -> None:
    with pytest.raises(ValueError, match="media_duration_s"):
        validate_time_range(10.0, 61.0, media_duration_s=60.0)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_values_are_rejected(value: float) -> None:
    with pytest.raises(ValueError, match="start_s"):
        validate_time_range(value, 10.0, media_duration_s=60.0)
    with pytest.raises(ValueError, match="end_s"):
        validate_time_range(0.0, value, media_duration_s=60.0)
    with pytest.raises(ValueError, match="media_duration_s"):
        validate_time_range(0.0, 10.0, media_duration_s=value)


@pytest.mark.parametrize("media_duration_s", [0.0, -1.0])
def test_non_positive_media_duration_is_rejected(media_duration_s: float) -> None:
    with pytest.raises(ValueError, match="media_duration_s"):
        validate_time_range(0.0, 1.0, media_duration_s=media_duration_s)
