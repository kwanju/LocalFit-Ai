"""CoachContextBuilder — repo-mocked context string output (ADR-013)."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.coach_context import CalendarSignals, CoachContextBuilder


def _profile(**kw):
    base = dict(
        name="홍길동",
        age=32,
        fitness_level=SimpleNamespace(value="intermediate"),
        goal="체력 증진",
        available_times='["mon","wed","fri"]',
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _session(id: int = 1):
    return SimpleNamespace(id=id, started_at=datetime(2026, 6, 1, 19, 0))


def _routine(name: str):
    return SimpleNamespace(name=name)


def _cond(fatigue: int):
    return SimpleNamespace(fatigue_level=fatigue, pain_report=None, notes=None)


def _set_log(session_id: int = 1):
    return SimpleNamespace(
        session_id=session_id, exercise_id=1, set_number=1, reps_completed=10
    )


@pytest.fixture
def builder() -> CoachContextBuilder:
    return CoachContextBuilder(
        profile_repo=AsyncMock(get=AsyncMock(return_value=_profile())),
        session_repo=AsyncMock(get_recent=AsyncMock(return_value=[_session(1)])),
        # 세션 1번은 set_log이 1개 있어 effective_session으로 카운트됨.
        set_repo=AsyncMock(get_by_session=AsyncMock(return_value=[_set_log(1)])),
        condition_repo=AsyncMock(get_by_session=AsyncMock(return_value=[_cond(7)])),
        routine_repo=AsyncMock(list_all=AsyncMock(return_value=[_routine("월수금 풀세트")])),
    )


class TestBuild:
    async def test_full_context(self, builder: CoachContextBuilder) -> None:
        ctx = await builder.build(now=datetime(2026, 6, 2, 19, 0))
        assert "32세" in ctx
        assert "intermediate" in ctx
        assert "체력 증진" in ctx
        assert "월수금 풀세트" in ctx
        assert "최근 세션 1회" in ctx
        assert "최근 피로도 7/10" in ctx
        assert "저녁" in ctx
        assert len(ctx) <= 700

    async def test_no_profile(self) -> None:
        b = CoachContextBuilder(
            profile_repo=AsyncMock(get=AsyncMock(return_value=None)),
            session_repo=AsyncMock(get_recent=AsyncMock(return_value=[])),
            set_repo=AsyncMock(get_by_session=AsyncMock(return_value=[])),
            condition_repo=AsyncMock(),
            routine_repo=AsyncMock(list_all=AsyncMock(return_value=[])),
        )
        ctx = await b.build(now=datetime(2026, 6, 2, 9, 0))
        assert "사용자 프로필 없음" in ctx
        assert "활성 루틴 없음" in ctx
        # SetLog 없는 사용자 — 신규 사용자로 표기 (2026-06-04 개정)
        assert "신규 사용자" in ctx
        assert "아침" in ctx

    async def test_sessions_without_set_logs_are_excluded(self) -> None:
        """연결만 하고 운동 안 한 세션(SetLog 없음)은 'history' 로 카운트하지 않는다."""
        sessions = [_session(1), _session(2), _session(3)]
        b = CoachContextBuilder(
            profile_repo=AsyncMock(get=AsyncMock(return_value=None)),
            session_repo=AsyncMock(get_recent=AsyncMock(return_value=sessions)),
            # 모든 세션에 SetLog 없음 → 빈 effective_sessions → 신규 사용자.
            set_repo=AsyncMock(get_by_session=AsyncMock(return_value=[])),
            condition_repo=AsyncMock(),
            routine_repo=AsyncMock(list_all=AsyncMock(return_value=[])),
        )
        ctx = await b.build(now=datetime(2026, 6, 2, 9, 0))
        assert "신규 사용자" in ctx
        assert "최근 세션" not in ctx

    async def test_calendar_signals_hook_phase8(self) -> None:
        async def signals() -> CalendarSignals:
            return CalendarSignals(
                weekly_pattern="월·수·금 주 3회",
                last_exercise={"푸시업": "5일 전"},
                rest_streak_days=2,
            )

        b = CoachContextBuilder(
            profile_repo=AsyncMock(get=AsyncMock(return_value=_profile())),
            session_repo=AsyncMock(get_recent=AsyncMock(return_value=[])),
            set_repo=AsyncMock(get_by_session=AsyncMock(return_value=[])),
            condition_repo=AsyncMock(),
            routine_repo=AsyncMock(list_all=AsyncMock(return_value=[])),
            calendar_signals_fn=signals,
        )
        ctx = await b.build(now=datetime(2026, 6, 2, 19, 0))
        assert "월·수·금 주 3회" in ctx
        assert "푸시업 5일 전" in ctx
        assert "휴식 streak 2일" in ctx

    async def test_calendar_signals_default_omits(self, builder: CoachContextBuilder) -> None:
        # Without phase-8 hook, the calendar lines are absent.
        ctx = await builder.build(now=datetime(2026, 6, 2, 9, 0))
        assert "주간 패턴" not in ctx
        assert "휴식 streak" not in ctx

    async def test_truncates_700(self) -> None:
        long_routines = [_routine("아주 긴 루틴 이름 " + str(i) * 50) for i in range(5)]
        b = CoachContextBuilder(
            profile_repo=AsyncMock(get=AsyncMock(return_value=_profile())),
            session_repo=AsyncMock(get_recent=AsyncMock(return_value=[])),
            set_repo=AsyncMock(get_by_session=AsyncMock(return_value=[])),
            condition_repo=AsyncMock(),
            routine_repo=AsyncMock(list_all=AsyncMock(return_value=long_routines)),
        )
        ctx = await b.build(now=datetime(2026, 6, 2, 9, 0))
        assert len(ctx) <= 700
