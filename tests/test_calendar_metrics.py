"""Unit tests for app.core.calendar_metrics pure functions (ADR-019, ADR-020)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

import pytest

from app.core.calendar_metrics import (
    DayStat,
    aggregate_daily,
    compute_last_exercise_dates,
    compute_level,
    compute_weekly_pattern,
    detect_rest_streak,
)

# ---------------------------------------------------------------------------
# Minimal duck-typed stubs (no SQLModel dependency in tests)
# ---------------------------------------------------------------------------


@dataclass
class _Session:
    id: int
    started_at: datetime
    ended_at: datetime | None = None


@dataclass
class _SetLog:
    id: int
    session_id: int
    exercise_id: int
    reps_completed: int | None
    duration_sec: int | None = None


@dataclass
class _Condition:
    id: int
    session_id: int
    fatigue_level: int | None


# ---------------------------------------------------------------------------
# compute_level
# ---------------------------------------------------------------------------


def test_level_no_workout() -> None:
    assert compute_level(0, 100) == 0


def test_level_above_75pct() -> None:
    assert compute_level(80, 100) == 4


def test_level_exactly_75pct() -> None:
    assert compute_level(75, 100) == 3


def test_level_50pct() -> None:
    assert compute_level(50, 100) == 2


def test_level_25pct() -> None:
    assert compute_level(25, 100) == 1


def test_level_zero_max_nonzero_volume() -> None:
    # No 30-day history yet — any workout → level 1
    assert compute_level(10, 0) == 1


def test_level_zero_volume() -> None:
    assert compute_level(0, 0) == 0


# ---------------------------------------------------------------------------
# aggregate_daily
# ---------------------------------------------------------------------------


def test_aggregate_daily_empty() -> None:
    assert aggregate_daily([], {}, {}, {}) == []


def test_aggregate_daily_single_session_no_logs() -> None:
    s = _Session(id=1, started_at=datetime(2026, 6, 1, 10, 0))
    result = aggregate_daily([s], {}, {}, {})
    assert len(result) == 1
    assert result[0].date == date(2026, 6, 1)
    assert result[0].volume == 0.0
    assert result[0].level == 0  # no set logs → volume 0


def test_aggregate_daily_volume_and_level() -> None:
    s = _Session(id=1, started_at=datetime(2026, 6, 1, 10, 0), ended_at=datetime(2026, 6, 1, 10, 30))
    set_logs = {1: [_SetLog(id=1, session_id=1, exercise_id=1, reps_completed=10)]}
    ex_names = {1: "푸시업"}

    result = aggregate_daily([s], set_logs, {}, ex_names)
    assert len(result) == 1
    ds = result[0]
    assert ds.volume == 10.0  # 10 reps × intensity 1.0
    assert ds.level >= 1
    assert "푸시업" in ds.exercises
    assert ds.sessions[0].duration_min == 30


def test_aggregate_daily_condition_avg() -> None:
    s = _Session(id=1, started_at=datetime(2026, 6, 1, 10, 0))
    conditions = {1: [_Condition(id=1, session_id=1, fatigue_level=8),
                      _Condition(id=2, session_id=1, fatigue_level=6)]}
    result = aggregate_daily([s], {}, conditions, {})
    assert result[0].condition_avg == pytest.approx(7.0)


def test_aggregate_daily_rolling_max_level() -> None:
    # Day 1: volume 100 (becomes max). Day 2: volume 50 → level 2 (50/100 = 50%).
    s1 = _Session(id=1, started_at=datetime(2026, 6, 1, 10, 0))
    s2 = _Session(id=2, started_at=datetime(2026, 6, 2, 10, 0))
    logs1 = [_SetLog(id=1, session_id=1, exercise_id=1, reps_completed=100)]
    logs2 = [_SetLog(id=2, session_id=2, exercise_id=1, reps_completed=50)]
    set_logs = {1: logs1, 2: logs2}
    ex_names = {1: "푸시업"}

    result = aggregate_daily([s1, s2], set_logs, {}, ex_names)
    assert result[0].level == 4   # 100/100 > 0.75
    assert result[1].level == 2   # 50/100 = 0.50


# ---------------------------------------------------------------------------
# compute_weekly_pattern
# ---------------------------------------------------------------------------


def test_weekly_pattern_empty() -> None:
    assert compute_weekly_pattern([]) is None


def test_weekly_pattern_mon_wed_fri() -> None:
    # 2026-06-01 = Monday, 06-03 = Wednesday, 06-05 = Friday
    sessions = [
        _Session(id=1, started_at=datetime(2026, 6, 1)),
        _Session(id=2, started_at=datetime(2026, 6, 3)),
        _Session(id=3, started_at=datetime(2026, 6, 5)),
    ]
    result = compute_weekly_pattern(sessions)
    assert result is not None
    assert "월" in result
    assert "수" in result
    assert "금" in result


def test_weekly_pattern_includes_frequency() -> None:
    # 6 sessions over 3 weeks (Jun 1 - Jun 19 = 19 days, 2.7 weeks → 6/2.7 ≈ 2 → "주 2회")
    # Jun 1,3,5 = Mon/Wed/Fri week1; Jun 8,10,12 = week2; Jun 15 = Mon week3 anchor
    sessions = [
        _Session(id=i, started_at=datetime(2026, 6, d))
        for i, d in enumerate([1, 3, 5, 8, 10, 12, 15, 17, 19], start=1)
    ]
    result = compute_weekly_pattern(sessions)
    assert result is not None
    # Pattern should mention days and frequency — exact value depends on span math
    assert "회" in result


# ---------------------------------------------------------------------------
# compute_last_exercise_dates
# ---------------------------------------------------------------------------


def test_last_exercise_dates_empty() -> None:
    assert compute_last_exercise_dates([], {}, {}) == {}


def test_last_exercise_dates_labels() -> None:
    now = datetime(2026, 6, 10)
    sessions = [
        _Session(id=1, started_at=datetime(2026, 6, 10)),  # today
        _Session(id=2, started_at=datetime(2026, 6, 9)),   # yesterday
        _Session(id=3, started_at=datetime(2026, 6, 5)),   # 5 days ago
    ]
    set_logs = {
        1: [_SetLog(id=1, session_id=1, exercise_id=1, reps_completed=10)],
        2: [_SetLog(id=2, session_id=2, exercise_id=2, reps_completed=10)],
        3: [_SetLog(id=3, session_id=3, exercise_id=3, reps_completed=10)],
    }
    ex_names = {1: "풀업", 2: "푸시업", 3: "스쿼트"}

    result = compute_last_exercise_dates(sessions, set_logs, ex_names, now)
    assert result["풀업"] == "오늘"
    assert result["푸시업"] == "어제"
    assert result["스쿼트"] == "5일 전"


# ---------------------------------------------------------------------------
# detect_rest_streak
# ---------------------------------------------------------------------------


def test_rest_streak_empty_sessions() -> None:
    assert detect_rest_streak([]) == 0


def test_rest_streak_worked_today() -> None:
    now = datetime(2026, 6, 10)
    sessions = [_Session(id=1, started_at=datetime(2026, 6, 10))]
    assert detect_rest_streak(sessions, now) == 0


def test_rest_streak_two_days() -> None:
    now = datetime(2026, 6, 10)
    sessions = [_Session(id=1, started_at=datetime(2026, 6, 8))]  # 2 days ago
    assert detect_rest_streak(sessions, now) == 2


def test_rest_streak_worked_yesterday() -> None:
    now = datetime(2026, 6, 10)
    sessions = [_Session(id=1, started_at=datetime(2026, 6, 9))]
    assert detect_rest_streak(sessions, now) == 1
