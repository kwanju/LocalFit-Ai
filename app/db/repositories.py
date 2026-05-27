from datetime import datetime, timezone

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models import (
    ConditionLog,
    InteractionLog,
    SessionStatus,
    SetLog,
    WorkoutSession,
)


class SessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, mode: str, routine_id: int | None = None) -> WorkoutSession:
        ws = WorkoutSession(mode=mode, routine_id=routine_id)
        self._session.add(ws)
        await self._session.commit()
        await self._session.refresh(ws)
        return ws

    async def get_by_id(self, session_id: int) -> WorkoutSession | None:
        return await self._session.get(WorkoutSession, session_id)

    async def end_session(self, session_id: int, status: SessionStatus) -> WorkoutSession | None:
        ws = await self.get_by_id(session_id)
        if ws is None:
            return None
        ws.ended_at = datetime.now(timezone.utc)
        ws.status = status
        self._session.add(ws)
        await self._session.commit()
        await self._session.refresh(ws)
        return ws

    async def get_recent(self, limit: int = 10) -> list[WorkoutSession]:
        result = await self._session.exec(
            select(WorkoutSession).order_by(WorkoutSession.started_at.desc()).limit(limit)
        )
        return list(result.all())


class SetLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        session_id: int,
        exercise_id: int,
        set_number: int,
        reps_completed: int | None = None,
        weight_kg: float | None = None,
        duration_sec: int | None = None,
    ) -> SetLog:
        log = SetLog(
            session_id=session_id,
            exercise_id=exercise_id,
            set_number=set_number,
            reps_completed=reps_completed,
            weight_kg=weight_kg,
            duration_sec=duration_sec,
        )
        self._session.add(log)
        await self._session.commit()
        await self._session.refresh(log)
        return log

    async def get_by_session(self, session_id: int) -> list[SetLog]:
        result = await self._session.exec(
            select(SetLog).where(SetLog.session_id == session_id)
        )
        return list(result.all())


class ConditionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        session_id: int,
        fatigue_level: int | None = None,
        pain_report: str | None = None,
        notes: str | None = None,
    ) -> ConditionLog:
        log = ConditionLog(
            session_id=session_id,
            fatigue_level=fatigue_level,
            pain_report=pain_report,
            notes=notes,
        )
        self._session.add(log)
        await self._session.commit()
        await self._session.refresh(log)
        return log

    async def get_by_session(self, session_id: int) -> list[ConditionLog]:
        result = await self._session.exec(
            select(ConditionLog).where(ConditionLog.session_id == session_id)
        )
        return list(result.all())


class InteractionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        session_id: int,
        role: str,
        content: str,
        input_mode: str | None = None,
    ) -> InteractionLog:
        log = InteractionLog(
            session_id=session_id,
            role=role,
            content=content,
            input_mode=input_mode,
        )
        self._session.add(log)
        await self._session.commit()
        await self._session.refresh(log)
        return log

    async def get_by_session(self, session_id: int) -> list[InteractionLog]:
        result = await self._session.exec(
            select(InteractionLog).where(InteractionLog.session_id == session_id)
        )
        return list(result.all())
