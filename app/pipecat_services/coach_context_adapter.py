"""DB-backed CoachContextBuilder adapter (ADR-012 pipecat_services tier).

Creates a fresh DB session on each build() call so the pipeline processor
does not hold an open connection across the full WebSocket lifetime.

Import chain:
  pipecat_services → core (CalendarSignals, CoachContextBuilder, calendar_metrics)
  pipecat_services → db  (repositories, engine)
Both are allowed per ADR-012 §의존 방향 규칙.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from loguru import logger
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import GoogleCalendarConfig
from app.core.calendar_metrics import (
    compute_last_exercise_dates,
    compute_weekly_pattern,
    detect_rest_streak,
)
from app.core.coach_context import CalendarSignals, CoachContextBuilder
from app.db.engine import create_db_session
from app.db.repositories import (
    ConditionRepository,
    ExerciseRepository,
    MemoryRepository,
    PlanRepository,
    RoutineRepository,
    SessionRepository,
    SetLogRepository,
    UserProfileRepository,
)


class DBCoachContextAdapter:
    """Adapter that satisfies the ``context_builder.build()`` duck-type expected
    by ``StructuredOllamaProcessor``, backed by a fresh DB session per call.
    """

    def __init__(
        self, *, calendar_pattern_weeks: int = 4, gcal_config: GoogleCalendarConfig | None = None
    ) -> None:
        self._weeks = calendar_pattern_weeks
        self._gcal_config = gcal_config

    async def build(self, *, recent_sessions: int = 5, now: datetime | None = None) -> str:
        async with create_db_session() as db:
            signals = await self._fetch_calendar_signals(db)
            # ADR-022 §9-3: 외부 Google Calendar 틈새 힌트(연동 시에만). 별도 소스라
            # 히트맵 신호와 분리해 채운다. 미연동/오프라인/실패면 None 으로 degrade.
            signals.free_gap_hint = await self._fetch_gap_hint(now)

            async def _get_signals() -> CalendarSignals:
                return signals

            builder = CoachContextBuilder(
                profile_repo=UserProfileRepository(db),
                session_repo=SessionRepository(db),
                set_repo=SetLogRepository(db),
                condition_repo=ConditionRepository(db),
                routine_repo=RoutineRepository(db),
                calendar_signals_fn=_get_signals,
                memory_repo=MemoryRepository(db),
                plan_repo=PlanRepository(db),
            )
            return await builder.build(recent_sessions=recent_sessions, now=now)

    async def _fetch_gap_hint(self, now: datetime | None) -> str | None:
        """Google Calendar 오늘 빈 시간 힌트(ADR-022 §9-3). 비연동/실패면 None."""
        if self._gcal_config is None or not self._gcal_config.enabled:
            return None
        try:
            from app.pipecat_services.calendar_sync import CalendarSyncService

            return await CalendarSyncService(self._gcal_config).today_gap_hint(now)
        except Exception as e:  # noqa: BLE001 — 틈새 힌트는 best-effort
            logger.warning("calendar gap hint failed: {}", e)
            return None

    async def _fetch_calendar_signals(self, db: AsyncSession) -> CalendarSignals:
        today = date.today()
        from_4w = today - timedelta(weeks=self._weeks)
        from_30d = today - timedelta(days=30)

        session_repo = SessionRepository(db)
        set_repo = SetLogRepository(db)
        ex_repo = ExerciseRepository(db)

        sessions_4w = await session_repo.get_range(from_4w, today)
        sessions_30d = await session_repo.get_range(from_30d, today)

        # SetLog가 없는 세션(연결만 하고 운동 안 한 세션)은 실제 운동 history가 아니므로
        # 패턴/streak/마지막운동일 계산에서 제외 (사용자 피드백 2026-06-04).
        all_session_ids = list(
            {s.id for s in (*sessions_4w, *sessions_30d) if s.id is not None}
        )
        set_logs_by_session: dict[int, list] = {}
        if all_session_ids:
            for sl in await set_repo.get_by_sessions(all_session_ids):
                set_logs_by_session.setdefault(sl.session_id, []).append(sl)

        def _has_sets(s) -> bool:
            return s.id is not None and bool(set_logs_by_session.get(s.id))

        effective_4w = [s for s in sessions_4w if _has_sets(s)]
        effective_30d = [s for s in sessions_30d if _has_sets(s)]

        all_exercises = await ex_repo.get_all()
        ex_names_by_id = {ex.id: ex.name for ex in all_exercises if ex.id is not None}

        try:
            weekly_pattern = compute_weekly_pattern(effective_4w)
            last_exercise = compute_last_exercise_dates(
                effective_30d, set_logs_by_session, ex_names_by_id
            )
            rest_streak = detect_rest_streak(effective_30d)
        except Exception as exc:  # noqa: BLE001 — calendar signals are best-effort
            logger.warning("calendar_signals computation failed: {}", exc)
            return CalendarSignals()

        return CalendarSignals(
            weekly_pattern=weekly_pattern,
            last_exercise=last_exercise if last_exercise else None,
            rest_streak_days=rest_streak,
        )
