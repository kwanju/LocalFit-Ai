"""WorkoutSession 저장소 — 종료/재활성(reactivate) (ADR-032 §구현 연계, 모드 전환 연속성).

reactivate 는 실제 DB enum(SessionStatus)을 건드리므로 mock 로는 못 잡던 회귀가 있었다:
초기 구현이 존재하지 않는 ``SessionStatus.active``(실제로는 PlanStatus 멤버)를 써서
런타임 ``AttributeError`` 로 터졌고, 모드 전환이 새 세션으로 떨어졌다(실세션 검증으로
발견). 이 테스트가 그 경로를 실제 DB 로 가드한다.
"""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.engine import init_db
from app.db.models import SessionStatus
from app.db.repositories import SessionRepository


@pytest.fixture
async def session(tmp_path):
    eng = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'sess.db'}",
        connect_args={"check_same_thread": False},
    )
    await init_db(engine=eng)
    factory = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await eng.dispose()


async def test_reactivate_restores_in_progress(session):
    repo = SessionRepository(session)
    ws = await repo.create(mode="c2c")
    await repo.end_session(ws.id, SessionStatus.completed)

    revived = await repo.reactivate(ws.id)
    assert revived is not None
    assert revived.status == SessionStatus.in_progress
    assert revived.ended_at is None  # 종료 스탬프 해제 — 같은 세션 이어가기


async def test_reactivate_missing_session_returns_none(session):
    assert await SessionRepository(session).reactivate(99999) is None
