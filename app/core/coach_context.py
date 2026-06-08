"""CoachContextBuilder — composes a 700-char natural-language context string
for every LLM call (ADR-013 §컨텍스트 빌더).

Pure domain code (ADR-012): repositories are injected, no Pipecat/FastAPI/
instructor imports here. Calendar-derived signals (weekly pattern, per-exercise
last performed, rest streak) are stubbed in phase 5 and wired up in phase 8 via
``app.core.calendar_metrics``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

_MAX_CONTEXT_CHARS: int = 700


class _ProfileRepo(Protocol):
    async def get(self): ...


class _SessionRepo(Protocol):
    async def get_recent(self, limit: int = 10): ...


class _SetLogRepo(Protocol):
    async def get_by_session(self, session_id: int): ...


class _ConditionRepo(Protocol):
    async def get_by_session(self, session_id: int): ...


class _RoutineRepo(Protocol):
    async def list_all(self): ...


def _time_of_day(now: datetime) -> str:
    h = now.hour
    if 5 <= h < 11:
        return "아침"
    if 11 <= h < 17:
        return "낮"
    if 17 <= h < 22:
        return "저녁"
    return "새벽"


def _profile_summary(profile) -> str:
    if profile is None:
        return "사용자 프로필 없음(온보딩 전)"
    parts: list[str] = []
    if profile.age:
        parts.append(f"{profile.age}세")
    level = getattr(profile, "fitness_level", None)
    if level is not None:
        parts.append(str(level.value if hasattr(level, "value") else level))
    if profile.goal:
        parts.append(f"목표 '{profile.goal}'")
    return f"사용자: {', '.join(parts)}" if parts else "사용자 프로필 미입력"


def _routine_summary(routines) -> str:
    if not routines:
        return "활성 루틴 없음"
    names = ", ".join(r.name for r in routines[:3])
    return f"활성 루틴: {names}"


def _recent_sessions_summary(sessions) -> str:
    """Summarise recent EFFECTIVE sessions (set_log이 1개 이상 있는 세션만).

    필터는 호출자가 미리 적용 — 빈 리스트는 신규 사용자로 취급한다.
    """
    if not sessions:
        return "신규 사용자 (운동 기록 없음)"
    return f"최근 세션 {len(sessions)}회 (가장 최근 {sessions[0].started_at:%m/%d %H시})"


@dataclass
class CalendarSignals:
    """Phase-8 hook — wired up by ``app.core.calendar_metrics`` later."""

    weekly_pattern: str | None = None       # e.g. "월·수·금 주 3회"
    last_exercise: dict[str, str] | None = None  # e.g. {"푸시업": "5일 전"}
    rest_streak_days: int = 0


@dataclass
class CoachContextBuilder:
    profile_repo: _ProfileRepo
    session_repo: _SessionRepo
    set_repo: _SetLogRepo
    condition_repo: _ConditionRepo
    routine_repo: _RoutineRepo
    calendar_signals_fn: object | None = None   # async () -> CalendarSignals; phase-8 wires it

    async def build(self, *, recent_sessions: int = 5, now: datetime | None = None) -> str:
        now = now or datetime.now()
        profile = await self.profile_repo.get()
        # over-fetch raw sessions, then keep only those with at least one SetLog
        # (연결만 하고 운동 안 한 세션은 LLM 컨텍스트에서 제외 — 신규 사용자 시나리오).
        raw_sessions = await self.session_repo.get_recent(limit=recent_sessions * 4)
        effective_sessions: list = []
        for s in raw_sessions:
            if s.id is None:
                continue
            try:
                sl = await self.set_repo.get_by_session(s.id)
            except Exception:  # noqa: BLE001 — best-effort
                sl = []
            if sl:
                effective_sessions.append(s)
                if len(effective_sessions) >= recent_sessions:
                    break
        sessions = effective_sessions
        routines = await self.routine_repo.list_all()

        latest_condition: str | None = None
        if sessions:
            try:
                cond_list = await self.condition_repo.get_by_session(sessions[0].id)
                if cond_list:
                    last = cond_list[-1]
                    if last.fatigue_level is not None:
                        latest_condition = f"최근 피로도 {last.fatigue_level}/10"
            except Exception:  # noqa: BLE001 — context is best-effort
                latest_condition = None

        signals = await self._calendar_signals()

        parts: list[str] = [
            _profile_summary(profile),
            _routine_summary(routines),
            _recent_sessions_summary(sessions),
        ]
        if latest_condition:
            parts.append(latest_condition)
        if signals.weekly_pattern:
            parts.append(f"주간 패턴: {signals.weekly_pattern}")
        if signals.last_exercise:
            last_str = ", ".join(f"{k} {v}" for k, v in signals.last_exercise.items())
            parts.append(f"운동별 마지막: {last_str}")
        if signals.rest_streak_days >= 2:
            parts.append(f"휴식 streak {signals.rest_streak_days}일")
        parts.append(f"현재 {_time_of_day(now)} {now.hour}시")

        context = " / ".join(parts)
        if len(context) > _MAX_CONTEXT_CHARS:
            context = context[: _MAX_CONTEXT_CHARS - 1] + "…"
        return context

    async def _calendar_signals(self) -> CalendarSignals:
        # Phase-8 wires app.core.calendar_metrics here. Until then return zeros
        # so the prompt simply omits weekly-pattern hints.
        if self.calendar_signals_fn is None:
            return CalendarSignals()
        try:
            result = await self.calendar_signals_fn()  # type: ignore[misc]
            if isinstance(result, CalendarSignals):
                return result
        except Exception:  # noqa: BLE001 — never break the prompt over a hook error
            pass
        return CalendarSignals()


def parse_available_times(profile) -> list[str]:
    """UserProfile.available_times is a JSON-encoded list; defensive parse."""
    raw = getattr(profile, "available_times", None)
    if not raw:
        return []
    try:
        return list(json.loads(raw))
    except (TypeError, ValueError):
        return []
