"""Phase v4-4 — PlanRepository (ADR-024).

주간 목표 생성 + 일자 분배 + 진척 추적(목표 대비 완료) + 조정(확답 후 호출 경로).
새 테이블은 create_all 이 만든다(마이그레이션 스텝 불필요).
"""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.plan import PlanGoalSpec
from app.db.engine import init_db
from app.db.models import PlanStatus
from app.db.repositories import PlanRepository


@pytest.fixture
async def session(tmp_path):
    eng = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'plan.db'}",
        connect_args={"check_same_thread": False},
    )
    await init_db(engine=eng)
    factory = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await eng.dispose()


async def test_create_plan_distributes_days(session):
    repo = PlanRepository(session)
    plan = await repo.create_plan(
        [PlanGoalSpec("푸시업", target_count=3, reps=10)]
    )
    assert plan.status == PlanStatus.active

    goals = await repo.list_goals(plan.id)
    assert len(goals) == 1
    assert goals[0].target_count == 3

    days = await repo.list_days(plan.id)
    # 3회 → 월·수·금 분배
    assert [d.weekday for d in days] == [0, 2, 4]
    assert all(not d.completed for d in days)


async def test_get_active_returns_latest_active(session):
    repo = PlanRepository(session)
    await repo.create_plan([PlanGoalSpec("스쿼트", 2, 15)])
    active = await repo.get_active()
    assert active is not None
    goals = await repo.list_goals(active.id)
    assert goals[0].exercise == "스쿼트"


async def test_new_plan_abandons_previous_active(session):
    """동시에 active 플랜은 하나 — 새 플랜 확정 시 이전 active 는 abandoned."""
    repo = PlanRepository(session)
    first = await repo.create_plan([PlanGoalSpec("푸시업", 3, 10)])
    second = await repo.create_plan([PlanGoalSpec("스쿼트", 2, 15)])

    active = await repo.get_active()
    assert active.id == second.id
    # 이전 플랜은 abandoned 로 정리됨
    await session.refresh(first)
    refreshed_first = await PlanRepository(session).get_active()
    assert refreshed_first.id != first.id


async def test_progress_derives_from_completed_days(session):
    repo = PlanRepository(session)
    plan = await repo.create_plan([PlanGoalSpec("푸시업", 3, 10)])

    # 처음엔 0/3
    prog = await repo.progress(plan.id)
    assert prog[0].completed_count == 0
    assert prog[0].target_count == 3

    # 한 칸 완료 → 1/3
    marked = await repo.mark_day_done(plan.id, "푸시업")
    assert marked is not None and marked.completed is True
    prog = await repo.progress(plan.id)
    assert prog[0].completed_count == 1


async def test_mark_day_done_returns_none_when_all_done(session):
    repo = PlanRepository(session)
    plan = await repo.create_plan([PlanGoalSpec("플랭크", 1, 30)])
    assert await repo.mark_day_done(plan.id, "플랭크") is not None
    # 더 이상 미완료 칸 없음
    assert await repo.mark_day_done(plan.id, "플랭크") is None


async def test_adjust_goal_lowers_target_and_reconciles_days(session):
    repo = PlanRepository(session)
    plan = await repo.create_plan([PlanGoalSpec("푸시업", 4, 10)])
    await repo.mark_day_done(plan.id, "푸시업")  # 1개 완료

    goal = await repo.adjust_goal(plan.id, "푸시업", new_target_count=2)
    assert goal is not None and goal.target_count == 2

    prog = await repo.progress(plan.id)
    assert prog[0].target_count == 2
    assert prog[0].completed_count == 1  # 완료한 칸은 보존
    # 총 칸 = 완료1 + 미완료1 = 2
    days = await repo.list_days(plan.id)
    pushup_days = [d for d in days if d.exercise == "푸시업"]
    assert len(pushup_days) == 2


async def test_adjust_goal_clamps_to_completed(session):
    """새 목표가 이미 완료한 수보다 작으면 완료 수로 클램프(과거 기록 보존)."""
    repo = PlanRepository(session)
    plan = await repo.create_plan([PlanGoalSpec("스쿼트", 3, 15)])
    await repo.mark_day_done(plan.id, "스쿼트")
    await repo.mark_day_done(plan.id, "스쿼트")  # 2개 완료

    goal = await repo.adjust_goal(plan.id, "스쿼트", new_target_count=1)
    assert goal.target_count == 2  # 완료 2개로 클램프
    prog = await repo.progress(plan.id)
    assert prog[0].completed_count == 2


async def test_adjust_goal_missing_returns_none(session):
    repo = PlanRepository(session)
    plan = await repo.create_plan([PlanGoalSpec("푸시업", 2, 10)])
    assert await repo.adjust_goal(plan.id, "플랭크", 1) is None


async def test_no_active_plan_when_none_created(session):
    assert await PlanRepository(session).get_active() is None
