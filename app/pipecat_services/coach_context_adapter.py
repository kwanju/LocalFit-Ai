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
    RoutineRepository,
    SessionRepository,
    SetLogRepository,
    UserProfileRepository,
)


class DBCoachContextAdapter:
    """Adapter that satisfies the ``context_builder.build()`` duck-type expected
    by ``StructuredOllamaProcessor``, backed by a fresh DB session per call.
    """

    def __init__(self, *, calendar_pattern_weeks: int = 4) -> None:
        self._weeks = calendar_pattern_weeks

    async def build(self, *, recent_sessions: int = 5, now: datetime | None = None) -> str:
        async with create_db_session() as db:
            signals = await self._fetch_calendar_signals(db)

            async def _get_signals() -> CalendarSignals:
                return signals

            builder = CoachContextBuilder(
                profile_repo=UserProfileRepository(db),
                session_repo=SessionRepository(db),
                set_repo=SetLogRepository(db),
                condition_repo=ConditionRepository(db),
                routine_repo=RoutineRepository(db),
                calendar_signals_fn=_get_signals,
            )
            return await builder.build(recent_sessions=recent_sessions, now=now)

    async def _fetch_calendar_signals(self, db) -> CalendarSignals:
        today = date.today()
        from_4w = today - timedelta(weeks=self._weeks)
        from_30d = today - timedelta(days=30)

        session_repo = SessionRepository(db)
        set_repo = SetLogRepository(db)
        ex_repo = ExerciseRepository(db)

        sessions_4w = await session_repo.get_range(from_4w, today)
        sessions_30d = await session_repo.get_range(from_30d, today)

        session_ids_30d = [s.id for s in sessions_30d if s.id is not None]
        set_logs_by_session: dict[int, list] = {}
        if session_ids_30d:
            for sl in await set_repo.get_by_sessions(session_ids_30d):
                set_logs_by_session.setdefault(sl.session_id, []).append(sl)

        all_exercises = await ex_repo.get_all()
        ex_names_by_id = {ex.id: ex.name for ex in all_exercises if ex.id is not None}

        try:
            weekly_pattern = compute_weekly_pattern(sessions_4w)
            last_exercise = compute_last_exercise_dates(
                sessions_30d, set_logs_by_session, ex_names_by_id
            )
            rest_streak = detect_rest_streak(sessions_30d)
        except Exception as exc:  # noqa: BLE001 — calendar signals are best-effort
            logger.warning("calendar_signals computation failed: {}", exc)
            return CalendarSignals()

        return CalendarSignals(
            weekly_pattern=weekly_pattern,
            last_exercise=last_exercise if last_exercise else None,
            rest_streak_days=rest_streak,
        )
