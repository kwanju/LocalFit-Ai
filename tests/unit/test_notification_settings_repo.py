"""Phase v4-8 — NotificationSettings 저장소 (ADR-027).

단일 행 시드(config 기본값) + 부분 갱신(화이트리스트). 새 테이블이라 create_all 이
만든다(마이그레이션 스텝 불필요).
"""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import NotificationsConfig
from app.db.engine import init_db
from app.db.repositories import NotificationSettingsRepository


@pytest.fixture
async def session(tmp_path):
    eng = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'notif.db'}",
        connect_args={"check_same_thread": False},
    )
    await init_db(engine=eng)
    factory = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await eng.dispose()


async def test_seeds_from_config_defaults(session):
    cfg = NotificationsConfig(lead_minutes=15, workout_time="07:30", mute_start=None)
    repo = NotificationSettingsRepository(session)
    row = await repo.get_or_create(cfg)
    assert row.id == 1
    assert row.lead_minutes == 15
    assert row.workout_time == "07:30"
    assert row.mute_start is None
    # 두 번째 호출은 같은 행(중복 생성 X)
    again = await repo.get_or_create(cfg)
    assert again.id == 1


async def test_update_whitelisted_fields(session):
    cfg = NotificationsConfig()
    repo = NotificationSettingsRepository(session)
    await repo.get_or_create(cfg)
    updated = await repo.update(cfg, enabled=False, mute_start="23:00", bogus="x")
    assert updated.enabled is False
    assert updated.mute_start == "23:00"
    # 미지정 필드는 보존
    assert updated.workout_time == cfg.workout_time
    # 알 수 없는 키는 무시(속성 안 생김)
    assert not hasattr(updated, "bogus") or getattr(updated, "bogus", None) is None
