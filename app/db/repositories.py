import json
from datetime import UTC, date, datetime, timedelta

from loguru import logger
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import DEFAULT_USER_ID, NotificationsConfig

# core/plan 은 외부 의존 0 인 순수 도메인(일자 분배·진척 값객체). db→core.plan 은
# import 사이클을 만들지 않는다(core.plan 은 어떤 것도 import 하지 않음). ADR-024.
from app.core.plan import GoalProgress, PlanGoalSpec, distribute_weekdays
from app.db.models import (
    DEFAULT_REST_SEC,
    ConditionLog,
    Exercise,
    FitnessBaseline,
    FitnessLevel,
    InteractionLog,
    MemoryFact,
    MemoryKind,
    NotificationSettings,
    PlanDay,
    PlanStatus,
    Routine,
    RoutineExercise,
    SessionStatus,
    SetLog,
    UserMemory,
    UserProfile,
    WeeklyGoal,
    WeeklyPlan,
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

    async def reactivate(self, session_id: int) -> WorkoutSession | None:
        """종료된 세션을 다시 active 로 되돌린다(ended_at 해제) — 모드 전환 시 같은
        세션을 이어가기 위함(ADR-032 §구현 연계, 세션 연속성). 단일 사용자라 별도 격리
        없이 id 로만 복원한다. 없으면 None."""
        ws = await self.get_by_id(session_id)
        if ws is None:
            return None
        ws.status = SessionStatus.in_progress
        ws.ended_at = None
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
        session_id: int | None = None,
        fatigue_level: int | None = None,
        soreness: int | None = None,
        pain_report: str | None = None,
        notes: str | None = None,
    ) -> ConditionLog:
        """체크인 저장(ADR-023). ``session_id=None`` 이면 세션 전 일일 체크인 —
        세션 생성 시 ``link_latest_unlinked`` 가 연결한다."""
        log = ConditionLog(
            session_id=session_id,
            fatigue_level=fatigue_level,
            soreness=soreness,
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

    async def latest(self) -> ConditionLog | None:
        """가장 최근 체크인(세션 연결 여부 무관). 코치 컨텍스트의 컨디션 신호용."""
        result = await self._session.exec(
            select(ConditionLog).order_by(ConditionLog.logged_at.desc()).limit(1)
        )
        return result.first()

    async def latest_unlinked(self, within_hours: int = 12) -> ConditionLog | None:
        """``within_hours`` 안의 세션 미연결 체크인 중 가장 최근 것(세션 연결 대상)."""
        cutoff = datetime.now(UTC) - timedelta(hours=within_hours)
        result = await self._session.exec(
            select(ConditionLog)
            .where(ConditionLog.session_id == None)  # noqa: E711 — SQLAlchemy IS NULL
            .where(ConditionLog.logged_at >= cutoff)
            .order_by(ConditionLog.logged_at.desc())
            .limit(1)
        )
        return result.first()

    async def link_latest_unlinked(
        self, session_id: int, within_hours: int = 12
    ) -> ConditionLog | None:
        """세션 전 체크인(session_id=None)을 새 세션에 연결. 없으면 None."""
        row = await self.latest_unlinked(within_hours=within_hours)
        if row is None:
            return None
        row.session_id = session_id
        self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        return row

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
        assessment: dict[str, int] | None = None,
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
        # 온보딩 자가보고 원본 시드 (ADR-028). 미입력(빈 dict)이면 기존 값을 덮어쓰지
        # 않는다 — 재온보딩 시 측정칸을 비워도 이전 시드를 보존한다.
        if assessment:
            profile.assessment_json = json.dumps(assessment, ensure_ascii=False)
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


def _week_start(today: date) -> date:
    """그 주의 월요일(주 시작). 단일 사용자(ADR-002)라 타임존 분기 없음."""
    return today - timedelta(days=today.weekday())


class PlanRepository:
    """주간 플랜 저장소 (ADR-024). 주간 목표(``WeeklyGoal``) + 일자 분배(``PlanDay``).

    조정(목표 변경)은 **확답 게이트 통과 후** 디스패처가 호출한다 — 저장소는 자동
    변경을 판단하지 않는다(회고 ConfirmRule 정신). 진척은 ``PlanDay`` 완료 행에서
    파생하므로 별도 카운터 동기화 버그가 없다.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_active(self) -> WeeklyPlan | None:
        """가장 최근 ``active`` 플랜. 없으면 None(→ 단발 제안 fallback, ADR-024)."""
        result = await self._session.exec(
            select(WeeklyPlan)
            .where(WeeklyPlan.status == PlanStatus.active)
            .order_by(WeeklyPlan.created_at.desc())
            .limit(1)
        )
        return result.first()

    async def create_plan(
        self,
        goals: list[PlanGoalSpec],
        *,
        week_start: date | None = None,
        note: str | None = None,
    ) -> WeeklyPlan:
        """새 주간 플랜 생성. 기존 ``active`` 플랜은 ``abandoned`` 로 정리(한 번에 하나).

        각 목표는 ``target_count`` 개의 ``PlanDay`` 로 한 주에 고르게 분배된다.
        """
        for stale in await self._active_plans():
            stale.status = PlanStatus.abandoned
            self._session.add(stale)

        plan = WeeklyPlan(week_start=week_start or _week_start(date.today()), note=note)
        self._session.add(plan)
        await self._session.commit()
        await self._session.refresh(plan)

        for spec in goals:
            self._session.add(
                WeeklyGoal(
                    plan_id=plan.id,
                    exercise=spec.exercise,
                    target_count=spec.target_count,
                    reps=spec.reps,
                )
            )
            for wd in distribute_weekdays(spec.target_count):
                self._session.add(
                    PlanDay(plan_id=plan.id, exercise=spec.exercise, weekday=wd)
                )
        await self._session.commit()
        await self._session.refresh(plan)
        return plan

    async def _active_plans(self) -> list[WeeklyPlan]:
        result = await self._session.exec(
            select(WeeklyPlan).where(WeeklyPlan.status == PlanStatus.active)
        )
        return list(result.all())

    async def list_goals(self, plan_id: int) -> list[WeeklyGoal]:
        result = await self._session.exec(
            select(WeeklyGoal).where(WeeklyGoal.plan_id == plan_id)
        )
        return list(result.all())

    async def list_days(self, plan_id: int) -> list[PlanDay]:
        result = await self._session.exec(
            select(PlanDay).where(PlanDay.plan_id == plan_id).order_by(PlanDay.weekday)
        )
        return list(result.all())

    async def progress(self, plan_id: int) -> list[GoalProgress]:
        """종목별 진척(목표 대비 완료). 완료 횟수는 ``PlanDay.completed`` 행 수에서 파생."""
        goals = await self.list_goals(plan_id)
        days = await self.list_days(plan_id)
        done_by_ex: dict[str, int] = {}
        for d in days:
            if d.completed:
                done_by_ex[d.exercise] = done_by_ex.get(d.exercise, 0) + 1
        return [
            GoalProgress(
                exercise=g.exercise,
                target_count=g.target_count,
                completed_count=done_by_ex.get(g.exercise, 0),
                reps=g.reps,
            )
            for g in goals
        ]

    async def mark_day_done(self, plan_id: int, exercise: str) -> PlanDay | None:
        """해당 종목의 가장 이른 미완료 칸 1개를 완료 처리. 없으면 None."""
        result = await self._session.exec(
            select(PlanDay)
            .where(PlanDay.plan_id == plan_id)
            .where(PlanDay.exercise == exercise)
            .where(PlanDay.completed == False)  # noqa: E712 — SQLAlchemy 표현식
            .order_by(PlanDay.weekday)
            .limit(1)
        )
        day = result.first()
        if day is None:
            return None
        day.completed = True
        day.completed_at = datetime.now(UTC)
        self._session.add(day)
        await self._session.commit()
        await self._session.refresh(day)
        return day

    async def adjust_goal(
        self, plan_id: int, exercise: str, new_target_count: int
    ) -> WeeklyGoal | None:
        """목표 횟수 조정(확답 게이트 통과 후만 호출). 완료한 칸은 보존하고, 미완료
        칸을 새 목표에 맞춰 재분배한다. ``new_target_count`` 가 이미 완료한 수보다
        작으면 완료 수로 클램프(과거 기록을 지우지 않음).

        대상 목표가 없으면 None.
        """
        result = await self._session.exec(
            select(WeeklyGoal)
            .where(WeeklyGoal.plan_id == plan_id)
            .where(WeeklyGoal.exercise == exercise)
        )
        goal = result.first()
        if goal is None:
            return None

        days = [
            d
            for d in await self.list_days(plan_id)
            if d.exercise == exercise
        ]
        completed = [d for d in days if d.completed]
        target = max(new_target_count, len(completed))
        goal.target_count = target
        self._session.add(goal)

        # 미완료 칸 전부 제거 후, (target - 완료수)개를 다시 분배.
        for d in days:
            if not d.completed:
                await self._session.delete(d)
        for wd in distribute_weekdays(target - len(completed)):
            self._session.add(PlanDay(plan_id=plan_id, exercise=exercise, weekday=wd))

        await self._session.commit()
        await self._session.refresh(goal)
        return goal

    async def set_status(self, plan_id: int, status: PlanStatus | str) -> None:
        plan = await self._session.get(WeeklyPlan, plan_id)
        if plan is None:
            logger.warning("set_status: weekly_plan {} not found", plan_id)
            return
        plan.status = PlanStatus(status)
        self._session.add(plan)
        await self._session.commit()


# 사용자 편집 가능한 알림 설정 필드 — PUT 으로 갱신 허용되는 화이트리스트.
_NOTIFICATION_FIELDS: frozenset[str] = frozenset(
    {
        "enabled",
        "lead_minutes",
        "workout_time",
        "mute_start",
        "mute_end",
        "checkin_enabled",
        "checkin_time",
    }
)


class NotificationSettingsRepository:
    """알림 설정 단일 행(id=1) 저장소 (ADR-027). config 기본값으로 시드 후 UI 가 갱신."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create(self, defaults: NotificationsConfig) -> NotificationSettings:
        """단일 행을 반환. 없으면 config 기본값으로 시드한다(첫 접근 시 1회)."""
        row = await self._session.get(NotificationSettings, 1)
        if row is not None:
            return row
        row = NotificationSettings(
            id=1,
            enabled=defaults.enabled,
            lead_minutes=defaults.lead_minutes,
            workout_time=defaults.workout_time,
            mute_start=defaults.mute_start,
            mute_end=defaults.mute_end,
            checkin_enabled=defaults.checkin_enabled,
            checkin_time=defaults.checkin_time,
        )
        self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        return row

    async def update(
        self, defaults: NotificationsConfig, **fields: object
    ) -> NotificationSettings:
        """화이트리스트 필드만 부분 갱신. 알 수 없는 키는 무시(방어적)."""
        row = await self.get_or_create(defaults)
        for key, value in fields.items():
            if key in _NOTIFICATION_FIELDS and value is not None:
                setattr(row, key, value)
        row.updated_at = datetime.now(UTC)
        self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        return row
