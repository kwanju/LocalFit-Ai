import json
import logging
from datetime import datetime, timezone

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import DEFAULT_USER_ID
from app.db.models import (
    DEFAULT_REST_SEC,
    ConditionLog,
    Exercise,
    FitnessLevel,
    InteractionLog,
    Routine,
    RoutineExercise,
    SessionStatus,
    SetLog,
    UserProfile,
    WorkoutSession,
)

logger = logging.getLogger(__name__)

# Terminal DB statuses that also stamp ended_at when first reached.
_ENDED_STATUSES: frozenset[SessionStatus] = frozenset(
    {SessionStatus.completed, SessionStatus.cancelled}
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

    async def update_status(self, session_id: int, status: str) -> None:
        """SessionPersister surface for the orchestrator (ADR-007). String status from core."""
        ws = await self.get_by_id(session_id)
        if ws is None:
            logger.warning("update_status: session %d not found", session_id)
            return
        db_status = SessionStatus(status)
        ws.status = db_status
        if db_status in _ENDED_STATUSES and ws.ended_at is None:
            ws.ended_at = datetime.now(timezone.utc)
        self._session.add(ws)
        await self._session.commit()

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


class ExerciseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_name(self, name: str) -> Exercise | None:
        result = await self._session.exec(select(Exercise).where(Exercise.name == name))
        return result.first()


class UserProfileRepository:
    """Single-user profile (ADR-002: always id=DEFAULT_USER_ID)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self) -> UserProfile | None:
        return await self._session.get(UserProfile, DEFAULT_USER_ID)

    async def upsert(
        self,
        *,
        name: str,
        fitness_level: FitnessLevel,
        available_times: list[str],
        goal: str | None = None,
        age: int | None = None,
        weight_kg: float | None = None,
        height_cm: float | None = None,
    ) -> UserProfile:
        profile = await self.get()
        if profile is None:
            profile = UserProfile(id=DEFAULT_USER_ID)
        profile.name = name
        profile.age = age
        profile.weight_kg = weight_kg
        profile.height_cm = height_cm
        profile.fitness_level = fitness_level
        profile.goal = goal
        profile.available_times = json.dumps(available_times, ensure_ascii=False)
        self._session.add(profile)
        await self._session.commit()
        await self._session.refresh(profile)
        return profile


class RoutineRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, name: str, description: str | None = None) -> Routine:
        routine = Routine(name=name, description=description)
        self._session.add(routine)
        await self._session.commit()
        await self._session.refresh(routine)
        return routine

    async def add_exercise(
        self,
        *,
        routine_id: int,
        exercise_id: int,
        sets: int,
        order_index: int,
        reps: int | None = None,
        duration_sec: int | None = None,
        rest_sec: int = DEFAULT_REST_SEC,
    ) -> RoutineExercise:
        link = RoutineExercise(
            routine_id=routine_id,
            exercise_id=exercise_id,
            sets=sets,
            reps=reps,
            duration_sec=duration_sec,
            rest_sec=rest_sec,
            order_index=order_index,
        )
        self._session.add(link)
        await self._session.commit()
        await self._session.refresh(link)
        return link

    async def get_by_id(self, routine_id: int) -> Routine | None:
        return await self._session.get(Routine, routine_id)

    async def list_all(self) -> list[Routine]:
        result = await self._session.exec(select(Routine).order_by(Routine.created_at.desc()))
        return list(result.all())

    async def list_exercises(self, routine_id: int) -> list[RoutineExercise]:
        result = await self._session.exec(
            select(RoutineExercise)
            .where(RoutineExercise.routine_id == routine_id)
            .order_by(RoutineExercise.order_index)
        )
        return list(result.all())

    async def delete(self, routine_id: int) -> bool:
        routine = await self.get_by_id(routine_id)
        if routine is None:
            return False
        for link in await self.list_exercises(routine_id):
            await self._session.delete(link)
        await self._session.delete(routine)
        await self._session.commit()
        return True
