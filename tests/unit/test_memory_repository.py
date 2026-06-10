"""Phase v4-2 — MemoryRepository (ADR-025).

1층 부상·제약 전량 조회/멱등 저장/해소, 1층 기준선 upsert, 2층 자유텍스트
최근순/키워드 검색을 검증한다.
"""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.engine import init_db
from app.db.models import MemoryKind
from app.db.repositories import MemoryRepository


@pytest.fixture
async def session(tmp_path):
    eng = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'mem.db'}",
        connect_args={"check_same_thread": False},
    )
    await init_db(engine=eng)  # create_all 이 신규 테이블도 만든다 (마이그레이션 스텝 불필요)
    factory = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await eng.dispose()


# --- 1층 부상·제약 ---------------------------------------------------------


async def test_add_and_get_constraints_returns_all_active(session):
    repo = MemoryRepository(session)
    await repo.add_constraint(MemoryKind.injury, "왼쪽 어깨 통증")
    await repo.add_constraint("constraint", "윗몸일으키기 금지", severity="high")

    constraints = await repo.get_constraints()
    assert len(constraints) == 2
    texts = {c.text for c in constraints}
    assert texts == {"왼쪽 어깨 통증", "윗몸일으키기 금지"}


async def test_add_constraint_is_idempotent(session):
    """동일 kind+text 활성 항목은 중복 저장 안 함(반복 발화 스팸 방지)."""
    repo = MemoryRepository(session)
    a = await repo.add_constraint(MemoryKind.injury, "무릎 통증")
    b = await repo.add_constraint(MemoryKind.injury, "  무릎 통증  ")  # 공백만 다름
    assert a.id == b.id
    assert len(await repo.get_constraints()) == 1


async def test_deactivate_constraint_drops_from_active(session):
    repo = MemoryRepository(session)
    mem = await repo.add_constraint(MemoryKind.injury, "발목 부상")
    assert await repo.deactivate_constraint(mem.id) is True
    assert await repo.get_constraints() == []


# --- 1층 기준선 ------------------------------------------------------------


async def test_set_baseline_upserts(session):
    repo = MemoryRepository(session)
    await repo.set_baseline("푸시업", "reps", 20)
    await repo.set_baseline("푸시업", "reps", 25)  # 같은 종목·지표 → 갱신
    await repo.set_baseline("플랭크", "duration_sec", 60)

    rows = {(b.exercise, b.metric): b.value for b in await repo.get_baseline()}
    assert rows == {("푸시업", "reps"): 25, ("플랭크", "duration_sec"): 60}


# --- 2층 자유텍스트 --------------------------------------------------------


async def test_recent_facts_newest_first(session):
    repo = MemoryRepository(session)
    await repo.add_fact("아침 운동을 선호함")
    await repo.add_fact("스쿼트를 싫어함", tags=["선호"])

    facts = await repo.recent_facts(limit=10)
    assert [f.text for f in facts] == ["스쿼트를 싫어함", "아침 운동을 선호함"]


async def test_search_facts_by_keyword(session):
    repo = MemoryRepository(session)
    await repo.add_fact("아침 운동을 선호함")
    await repo.add_fact("저녁엔 피곤함")

    hits = await repo.search_facts("아침")
    assert len(hits) == 1
    assert hits[0].text == "아침 운동을 선호함"
    assert await repo.search_facts("없는키워드") == []
