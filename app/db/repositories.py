import json
from datetime import UTC, date, datetime, timedelta

from loguru import logger
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import DEFAULT_USER_ID
from app.db.models import (
    DEFAULT_REST_SEC,
    ConditionLog,
    Exercise,
    FitnessBaseline,
    FitnessLevel,
    InteractionLog,
    MemoryFact,
    MemoryKind,
    Routine,
    RoutineExercise,
    SessionStatus,
    SetLog,
    UserMemory,
    UserProfile,
    WorkoutSession,
)

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
        ws.ended_at = datetime.now(UTC)
        ws.status = status
        self._session.add(ws)
        await self._session.commit()
        await self._session.refresh(ws)
        return ws

    async def update_status(self, session_id: int, status: str) -> None:
        """Update workout-session status by string value (ADR-008). Auto-stamps
        ``ended_at`` when transitioning to a terminal status."""
        ws = await self.get_by_id(session_id)
        if ws is None:
            logger.warning("update_status: session %d not found", session_id)
            return
        db_status = SessionStatus(status)
        ws.status = db_status
        if db_status in _ENDED_STATUSES and ws.ended_at is None:
            ws.ended_at = datetime.now(UTC)
        self._session.add(ws)
        await self._session.commit()

    async def get_recent(self, limit: int = 10) -> list[WorkoutSession]:
        result = await self._session.exec(
            select(WorkoutSession).order_by(WorkoutSession.started_at.desc()).limit(limit)
        )
        return list(result.all())

    async def get_range(self, from_: date, to: date) -> list[WorkoutSession]:
        """Return sessions whose started_at falls within [from_, to] (inclusive). (ADR-020)"""
        from_dt = datetime(from_.year, from_.month, from_.day, tzinfo=UTC)
        to_next = to + timedelta(days=1)
        to_dt = datetime(to_next.year, to_next.month, to_next.day, tzinfo=UTC)
        result = await self._session.exec(
            select(WorkoutSession)
            .where(WorkoutSession.started_at >= from_dt)
            .where(WorkoutSession.started_at < to_dt)
            .order_by(WorkoutSession.started_at)
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

    async def get_by_sessions(self, session_ids: list[int]) -> list[SetLog]:
        """Batch-fetch set logs for multiple sessions (ADR-020 §캘린더 API)."""
        if not session_ids:
            return []
        result = await self._session.exec(
            select(SetLog).where(SetLog.session_id.in_(session_ids))  # type: ignore[union-attr]
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

    async def get_by_sessions(self, session_ids: list[int]) -> list[ConditionLog]:
        """Batch-fetch condition logs for multiple sessions (ADR-020 §캘린더 API)."""
        if not session_ids:
            return []
        result = await self._session.exec(
            select(ConditionLog).where(ConditionLog.session_id.in_(session_ids))  # type: ignore[union-attr]
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

    async def get_all(self) -> list[Exercise]:
        result = await self._session.exec(select(Exercise))
        return list(result.all())


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


class MemoryRepository:
    """영속 메모리 저장소 (ADR-025). 1층=부상·제약(전량 주입), 2층=자유텍스트.

    단일 사용자(ADR-002)라 ``user_id`` 분기 없음.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- 1층: 부상·제약 (안전, 전량 조회) ---------------------------------

    async def get_constraints(self) -> list[UserMemory]:
        """활성 부상·제약 전량(오래된 순). 컨텍스트 빌더가 cap 면제로 전량 주입한다."""
        result = await self._session.exec(
            select(UserMemory)
            .where(UserMemory.active == True)  # noqa: E712 — SQLAlchemy 표현식
            .order_by(UserMemory.created_at)
        )
        return list(result.all())

    async def add_constraint(
        self,
        kind: MemoryKind | str,
        text: str,
        severity: str | None = None,
    ) -> UserMemory:
        """부상·제약 추가. 동일 ``kind``+``text`` 활성 항목이 있으면 중복 저장하지
        않고 기존 항목을 돌려준다(같은 발화 반복 시 스팸 방지 — 멱등)."""
        kind = MemoryKind(kind)
        norm = text.strip()
        existing = await self._session.exec(
            select(UserMemory)
            .where(UserMemory.active == True)  # noqa: E712
            .where(UserMemory.kind == kind)
            .where(UserMemory.text == norm)
        )
        found = existing.first()
        if found is not None:
            return found
        mem = UserMemory(kind=kind, text=norm, severity=severity)
        self._session.add(mem)
        await self._session.commit()
        await self._session.refresh(mem)
        return mem

    async def deactivate_constraint(self, memory_id: int) -> bool:
        """제약 해소(이력 보존 — 삭제 아님)."""
        mem = await self._session.get(UserMemory, memory_id)
        if mem is None:
            return False
        mem.active = False
        self._session.add(mem)
        await self._session.commit()
        return True

    # --- 1층: 기준선 (phase v4-5 가 채움, 여기선 upsert 만 제공) -----------

    async def set_baseline(
        self,
        exercise: str,
        metric: str,
        value: int,
        note: str | None = None,
    ) -> FitnessBaseline:
        """종목·지표별 기준선 upsert."""
        result = await self._session.exec(
            select(FitnessBaseline)
            .where(FitnessBaseline.exercise == exercise)
            .where(FitnessBaseline.metric == metric)
        )
        row = result.first()
        if row is None:
            row = FitnessBaseline(exercise=exercise, metric=metric, value=value, note=note)
        else:
            row.value = value
            row.note = note
            row.updated_at = datetime.now(UTC)
        self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        return row

    async def get_baseline(self) -> list[FitnessBaseline]:
        result = await self._session.exec(select(FitnessBaseline))
        return list(result.all())

    # --- 2층: 자유텍스트 메모 (최근순 / 키워드, 벡터 X) -------------------

    async def add_fact(self, text: str, tags: list[str] | None = None) -> MemoryFact:
        fact = MemoryFact(
            text=text.strip(),
            tags=json.dumps(tags or [], ensure_ascii=False),
        )
        self._session.add(fact)
        await self._session.commit()
        await self._session.refresh(fact)
        return fact

    async def recent_facts(self, limit: int = 10) -> list[MemoryFact]:
        result = await self._session.exec(
            select(MemoryFact).order_by(MemoryFact.created_at.desc()).limit(limit)
        )
        return list(result.all())

    async def search_facts(self, keyword: str, limit: int = 10) -> list[MemoryFact]:
        kw = keyword.strip()
        if not kw:
            return []
        result = await self._session.exec(
            select(MemoryFact)
            .where(MemoryFact.text.contains(kw))  # type: ignore[union-attr]
            .order_by(MemoryFact.created_at.desc())
            .limit(limit)
        )
        return list(result.all())


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
