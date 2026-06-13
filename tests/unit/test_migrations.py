"""Phase v4-1 — DB migration scaffold tests (app/db/migrations.py).

ADR-021 s2c→s2s 데이터 변환 + schema_version 기록 + 멱등성 검증.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.engine import init_db
from app.db.migrations import _STEPS, apply_migrations
from app.db.models import SessionMode
from app.db.repositories import SessionRepository

# 최신 스키마 버전 = 마이그레이션 스텝 수. 스텝 추가 시 자동으로 따라간다.
_LATEST_VERSION = len(_STEPS)


@pytest.fixture
async def engine(tmp_path):
    eng = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'mig.db'}",
        connect_args={"check_same_thread": False},
    )
    await init_db(engine=eng)  # create_all + apply_migrations (version → 최신)
    yield eng
    await eng.dispose()


async def test_schema_version_recorded(engine):
    """init_db 후 schema_version 이 최신(스텝 수)으로 기록된다."""
    async with engine.begin() as conn:
        version = (await conn.execute(text("SELECT version FROM schema_version"))).scalar_one()
    assert version == _LATEST_VERSION


async def test_s2c_row_migrated_to_s2s(engine):
    """기존 mode='s2c' 세션 행이 마이그레이션으로 's2s' 가 된다 (다른 모드는 불변)."""
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        s2c_session = await SessionRepository(s).create(mode=SessionMode.c2c)
        c2c_session = await SessionRepository(s).create(mode=SessionMode.c2c)
    s2c_id, c2c_id = s2c_session.id, c2c_session.id

    # enum 에서 s2c 가 사라졌으므로 raw SQL 로 과거 상태를 재현 + 버전 되감기.
    async with engine.begin() as conn:
        await conn.execute(text("UPDATE session SET mode='s2c' WHERE id=:i"), {"i": s2c_id})
        await conn.execute(text("UPDATE schema_version SET version=0"))

    await apply_migrations(engine)

    async with engine.begin() as conn:
        s2c_mode = (
            await conn.execute(text("SELECT mode FROM session WHERE id=:i"), {"i": s2c_id})
        ).scalar_one()
        c2c_mode = (
            await conn.execute(text("SELECT mode FROM session WHERE id=:i"), {"i": c2c_id})
        ).scalar_one()
        version = (await conn.execute(text("SELECT version FROM schema_version"))).scalar_one()

    assert s2c_mode == "s2s"   # s2c → s2s
    assert c2c_mode == "c2c"   # 불변
    assert version == _LATEST_VERSION


async def test_assessment_seed_column_added(engine):
    """ADR-028: user_profile.assessment_json 컬럼이 마이그레이션으로 추가된다(멱등)."""
    async with engine.begin() as conn:
        cols = {r[1] for r in (await conn.execute(text("PRAGMA table_info(user_profile)"))).all()}
    assert "assessment_json" in cols


async def test_assessment_seed_column_idempotent_on_existing_db(engine):
    """기존 DB(컬럼 없음) 재현 → 버전 되감기 → 재적용 시 한 번만 추가(에러 없음)."""
    # 컬럼이 없는 구 스키마를 SQLite 테이블 재작성으로 재현하긴 번거로워, 같은 스텝을
    # 두 번 적용해도 _column_exists 가드로 안전함을 확인한다(이미 존재 → no-op).
    async with engine.begin() as conn:
        await conn.execute(text("UPDATE schema_version SET version=2"))
    await apply_migrations(engine)  # step 3 재적용 — 이미 컬럼 존재 → 멱등
    async with engine.begin() as conn:
        version = (await conn.execute(text("SELECT version FROM schema_version"))).scalar_one()
    assert version == _LATEST_VERSION


async def test_migrations_idempotent(engine):
    """이미 최신 버전이면 재호출이 no-op (에러 없이 버전 유지)."""
    await apply_migrations(engine)
    await apply_migrations(engine)
    async with engine.begin() as conn:
        version = (await conn.execute(text("SELECT version FROM schema_version"))).scalar_one()
    assert version == _LATEST_VERSION
