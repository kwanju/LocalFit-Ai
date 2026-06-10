import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.engine import init_db
from app.db.models import (
    CountingMode,
    Exercise,
    SessionMode,
    SessionStatus,
)
from app.db.repositories import (
    ConditionRepository,
    InteractionRepository,
    SessionRepository,
    SetLogRepository,
)


@pytest.fixture
async def tmp_db(tmp_path):
    """Isolated async SQLite DB per test — no config.yaml required."""
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    await init_db(engine=engine)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(tmp_db):
    factory = async_sessionmaker(tmp_db, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


async def test_all_tables_created(tmp_db):
    async with tmp_db.connect() as conn:
        tables = await conn.run_sync(lambda c: inspect(c).get_table_names())
    expected = {
        "user_profile",
        "exercise",
        "routine",
        "routine_exercise",
        "session",
        "set_log",
        "condition_log",
        "interaction_log",
    }
    assert expected.issubset(set(tables))


async def test_exercise_seed_inserted(db_session):
    exercises = list((await db_session.exec(select(Exercise))).all())
    assert len(exercises) == 4
    names = {e.name for e in exercises}
    assert names == {"풀업", "푸시업", "스쿼트", "플랭크"}


async def test_exercise_counting_modes(db_session):
    plank = (await db_session.exec(select(Exercise).where(Exercise.name == "플랭크"))).first()
    pullup = (await db_session.exec(select(Exercise).where(Exercise.name == "풀업"))).first()
    assert plank is not None and plank.counting_mode == CountingMode.timer
    assert pullup is not None and pullup.counting_mode == CountingMode.metronome


async def test_seed_is_idempotent(tmp_db):
    await init_db(engine=tmp_db)
    factory = async_sessionmaker(tmp_db, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        count = len(list((await session.exec(select(Exercise))).all()))
    assert count == 4


async def test_session_repository_create(db_session):
    repo = SessionRepository(db_session)
    ws = await repo.create(mode=SessionMode.c2c)
    assert ws.id is not None
    assert ws.status == SessionStatus.in_progress
    assert ws.mode == SessionMode.c2c


async def test_session_repository_end(db_session):
    repo = SessionRepository(db_session)
    ws = await repo.create(mode=SessionMode.s2s)
    ended = await repo.end_session(ws.id, SessionStatus.completed)
    assert ended is not None
    assert ended.status == SessionStatus.completed
    assert ended.ended_at is not None


async def test_session_repository_get_recent(db_session):
    repo = SessionRepository(db_session)
    await repo.create(mode=SessionMode.c2c)
    await repo.create(mode=SessionMode.c2s)
    recent = await repo.get_recent(limit=5)
    assert len(recent) == 2


async def test_set_log_repository(db_session):
    exercise = (
        await db_session.exec(select(Exercise).where(Exercise.name == "푸시업"))
    ).first()
    assert exercise is not None
    ws = await SessionRepository(db_session).create(mode=SessionMode.c2c)
    repo = SetLogRepository(db_session)
    log = await repo.create(
        session_id=ws.id,
        exercise_id=exercise.id,
        set_number=1,
        reps_completed=10,
    )
    assert log.id is not None
    assert log.reps_completed == 10


async def test_condition_repository(db_session):
    ws = await SessionRepository(db_session).create(mode=SessionMode.c2c)
    repo = ConditionRepository(db_session)
    log = await repo.create(session_id=ws.id, fatigue_level=7, soreness=3, notes="조금 피곤함")
    assert log.id is not None
    assert log.fatigue_level == 7
    assert log.soreness == 3


async def test_condition_checkin_links_to_session(db_session):
    """ADR-023: 세션 전 체크인(session_id=None)을 세션 생성 시 연결한다."""
    repo = ConditionRepository(db_session)
    checkin = await repo.create(fatigue_level=6, soreness=4, notes="어깨 뻐근")
    assert checkin.session_id is None  # 세션 전 — nullable 컬럼

    ws = await SessionRepository(db_session).create(mode=SessionMode.c2c)
    linked = await repo.link_latest_unlinked(ws.id)
    assert linked is not None
    assert linked.id == checkin.id
    assert linked.session_id == ws.id

    # 연결 후엔 세션 조회로 보이고, 미연결 체크인은 더 없다.
    by_session = await repo.get_by_session(ws.id)
    assert any(c.id == checkin.id for c in by_session)
    assert await repo.latest_unlinked() is None


async def test_condition_latest_returns_most_recent(db_session):
    repo = ConditionRepository(db_session)
    await repo.create(fatigue_level=4)
    newest = await repo.create(fatigue_level=9, soreness=5)
    latest = await repo.latest()
    assert latest is not None
    assert latest.id == newest.id
    assert latest.fatigue_level == 9


async def test_interaction_repository(db_session):
    ws = await SessionRepository(db_session).create(mode=SessionMode.c2c)
    repo = InteractionRepository(db_session)
    log = await repo.create(
        session_id=ws.id,
        role="user",
        content="안녕하세요",
        input_mode="text",
    )
    assert log.id is not None
    assert log.content == "안녕하세요"
    assert log.role == "user"
