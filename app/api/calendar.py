"""Calendar API — GET /api/calendar (ADR-020)."""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.calendar_metrics import aggregate_daily
from app.db.engine import get_session
from app.db.repositories import (
    ConditionRepository,
    ExerciseRepository,
    SessionRepository,
    SetLogRepository,
)

router = APIRouter(prefix="/api", tags=["calendar"])


class SessionSummaryOut(BaseModel):
    id: int
    started_at: str
    duration_min: int | None


class DayStatOut(BaseModel):
    date: date
    level: int
    volume: float
    sessions: list[SessionSummaryOut]
    exercises: list[str]
    condition_avg: float | None


@router.get("/calendar", response_model=list[DayStatOut])
async def get_calendar(
    from_: date | None = Query(None, alias="from"),
    to: date | None = None,
    db: AsyncSession = Depends(get_session),
) -> list[DayStatOut]:
    """Return per-day workout intensity stats for the given date range.

    Defaults to the last 365 days when from/to are omitted.
    Days with no sessions are not included (treated as level 0 by the client).
    """
    today = date.today()
    from_date = from_ or (today - timedelta(days=365))
    to_date = to or today

    session_repo = SessionRepository(db)
    set_repo = SetLogRepository(db)
    condition_repo = ConditionRepository(db)
    exercise_repo = ExerciseRepository(db)

    sessions = await session_repo.get_range(from_date, to_date)
    session_ids = [s.id for s in sessions if s.id is not None]

    set_logs_by_session: dict[int, list] = {}
    conditions_by_session: dict[int, list] = {}

    if session_ids:
        for sl in await set_repo.get_by_sessions(session_ids):
            set_logs_by_session.setdefault(sl.session_id, []).append(sl)
        for c in await condition_repo.get_by_sessions(session_ids):
            conditions_by_session.setdefault(c.session_id, []).append(c)

    all_exercises = await exercise_repo.get_all()
    exercise_names_by_id = {ex.id: ex.name for ex in all_exercises if ex.id is not None}

    day_stats = aggregate_daily(
        sessions,
        set_logs_by_session,
        conditions_by_session,
        exercise_names_by_id,
    )

    return [
        DayStatOut(
            date=ds.date,
            level=ds.level,
            volume=ds.volume,
            sessions=[
                SessionSummaryOut(
                    id=s.id,
                    started_at=s.started_at,
                    duration_min=s.duration_min,
                )
                for s in ds.sessions
            ],
            exercises=ds.exercises,
            condition_avg=ds.condition_avg,
        )
        for ds in day_stats
    ]
