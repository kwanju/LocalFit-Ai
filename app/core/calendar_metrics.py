"""Pure domain functions for calendar-based workout metrics (ADR-020, ADR-012).

No Pipecat / FastAPI / SQLModel / transformers imports — domain core layer.
All inputs are duck-typed so the DB models can evolve without touching here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

# MVP: all exercises have equal intensity weight (ADR-020 §강도 산정 식)
# Post-MVP: tune these per user feedback (config.yaml 조정 가능).
EXERCISE_INTENSITY: dict[str, float] = {
    "풀업": 1.0,
    "푸시업": 1.0,
    "스쿼트": 1.0,
    "플랭크": 1.0,
}
_DEFAULT_INTENSITY: float = 1.0

_WEEKDAY_KO: tuple[str, ...] = ("월", "화", "수", "목", "금", "토", "일")


@dataclass
class SessionSummary:
    id: int
    started_at: str  # ISO-format string
    duration_min: int | None


@dataclass
class DayStat:
    date: date
    level: int  # 0-4 (ADR-020 §강도 산정 식)
    volume: float
    sessions: list[SessionSummary] = field(default_factory=list)
    exercises: list[str] = field(default_factory=list)
    condition_avg: float | None = None


def _to_date(dt: Any) -> date:
    if isinstance(dt, datetime):
        return dt.date()
    if isinstance(dt, date):
        return dt
    raise TypeError(f"Expected datetime or date, got {type(dt)}")


def compute_level(volume_today: float, max_volume_30d: float) -> int:
    """Map (volume_today, rolling-30d-max) → GitHub-style heat level 0-4.

    ADR-020 §강도 산정 식:
      0 = no exercise, 1-4 = 0-25% / 25-50% / 50-75% / 75-100% of rolling max.
    """
    if volume_today <= 0:
        return 0
    if max_volume_30d <= 0:
        return 1
    ratio = volume_today / max_volume_30d
    if ratio <= 0.25:
        return 1
    if ratio <= 0.50:
        return 2
    if ratio <= 0.75:
        return 3
    return 4


def aggregate_daily(
    sessions: list[Any],
    set_logs_by_session: dict[int, list[Any]],
    conditions_by_session: dict[int, list[Any]],
    exercise_names_by_id: dict[int, str],
) -> list[DayStat]:
    """Aggregate sessions + set logs + conditions into per-day DayStat list.

    Returns only days that have at least one session (calendar API consumer
    treats missing days as level 0 implicitly).
    """
    by_date: dict[date, list[Any]] = {}
    for s in sessions:
        day = _to_date(s.started_at)
        by_date.setdefault(day, []).append(s)

    vol_by_date: dict[date, float] = {}
    for day, day_sessions in by_date.items():
        vol = 0.0
        for s in day_sessions:
            for sl in set_logs_by_session.get(s.id, []):
                name = exercise_names_by_id.get(sl.exercise_id, "")
                intensity = EXERCISE_INTENSITY.get(name, _DEFAULT_INTENSITY)
                reps = sl.reps_completed or 0
                vol += reps * intensity
        vol_by_date[day] = vol

    result: list[DayStat] = []
    for day in sorted(by_date):
        vol = vol_by_date[day]
        cutoff = day - timedelta(days=30)
        max_vol_30d = max(
            (v for d, v in vol_by_date.items() if cutoff <= d <= day),
            default=0.0,
        )

        day_sessions = by_date[day]
        summaries: list[SessionSummary] = []
        for s in day_sessions:
            duration: int | None = None
            if s.started_at is not None and s.ended_at is not None:
                delta = s.ended_at - s.started_at
                duration = max(0, int(delta.total_seconds() / 60))
            started_str = (
                s.started_at.isoformat()
                if hasattr(s.started_at, "isoformat")
                else str(s.started_at)
            )
            summaries.append(
                SessionSummary(id=s.id, started_at=started_str, duration_min=duration)
            )

        ex_names: list[str] = []
        seen: set[str] = set()
        for s in day_sessions:
            for sl in set_logs_by_session.get(s.id, []):
                name = exercise_names_by_id.get(sl.exercise_id, "")
                if name and name not in seen:
                    ex_names.append(name)
                    seen.add(name)

        fatigue_vals: list[int] = []
        for s in day_sessions:
            for c in conditions_by_session.get(s.id, []):
                if c.fatigue_level is not None:
                    fatigue_vals.append(c.fatigue_level)
        cond_avg = sum(fatigue_vals) / len(fatigue_vals) if fatigue_vals else None

        result.append(
            DayStat(
                date=day,
                level=compute_level(vol, max_vol_30d),
                volume=vol,
                sessions=summaries,
                exercises=ex_names,
                condition_avg=cond_avg,
            )
        )
    return result


def compute_weekly_pattern(sessions: list[Any]) -> str | None:
    """Summarize workout days-of-week pattern like '월·수·금 주 3회'.

    Input: list of sessions with duck-typed `.started_at` datetime/date.
    """
    if not sessions:
        return None

    weekday_set: set[int] = set()
    for s in sessions:
        weekday_set.add(_to_date(s.started_at).weekday())  # 0=Mon, 6=Sun

    day_str = "·".join(_WEEKDAY_KO[d] for d in sorted(weekday_set))

    dates = sorted(_to_date(s.started_at) for s in sessions)
    span_days = max((dates[-1] - dates[0]).days + 1, 7)
    avg_per_week = round(len(sessions) / (span_days / 7))
    return f"{day_str} 주 {avg_per_week}회"


def compute_last_exercise_dates(
    sessions: list[Any],
    set_logs_by_session: dict[int, list[Any]],
    exercise_names_by_id: dict[int, str],
    now: datetime | None = None,
) -> dict[str, str]:
    """Return per-exercise last-performed label like {'푸시업': '5일 전'}.

    Only exercises with at least one set log are included.
    """
    now_dt = now if now is not None else datetime.now()
    today = now_dt.date() if isinstance(now_dt, datetime) else now_dt  # type: ignore[union-attr]

    last_dates: dict[str, date] = {}
    for s in sessions:
        day = _to_date(s.started_at)
        for sl in set_logs_by_session.get(s.id, []):
            name = exercise_names_by_id.get(sl.exercise_id, "")
            if not name:
                continue
            if name not in last_dates or day > last_dates[name]:
                last_dates[name] = day

    result: dict[str, str] = {}
    for name, last in last_dates.items():
        diff = (today - last).days
        if diff == 0:
            result[name] = "오늘"
        elif diff == 1:
            result[name] = "어제"
        else:
            result[name] = f"{diff}일 전"
    return result


def detect_rest_streak(sessions: list[Any], now: datetime | None = None) -> int:
    """Count consecutive rest days counting back from today (0 = worked out today)."""
    now_dt = now if now is not None else datetime.now()
    today = now_dt.date() if isinstance(now_dt, datetime) else now_dt  # type: ignore[union-attr]

    if not sessions:
        return 0

    workout_dates: set[date] = {_to_date(s.started_at) for s in sessions}

    streak = 0
    for days_back in range(366):  # cap at ~1 year for safety
        check = today - timedelta(days=days_back)
        if check in workout_dates:
            break
        streak += 1
    return streak
