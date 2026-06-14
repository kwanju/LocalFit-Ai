"""Phase v4-8 — 능동 알림 스케줄 API (ADR-027).

설정 라운드트립 + due/pending/ack 경로. 시각 의존 판정은 순수 코어
(tests/unit/test_schedule.py)가 커버하므로 여기서는 엔드포인트 배선·DB 연동·ack 흐름을
결정적으로 본다(checkin_time=00:00 → 하루 중 언제 돌려도 이미 지난 시점).
"""

import asyncio
from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api import schedule as schedule_api
from app.db.engine import get_session, init_db
from app.main import app


@pytest.fixture
def client(tmp_path) -> AsyncIterator[TestClient]:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'sched.db'}", poolclass=NullPool
    )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    asyncio.run(init_db(engine=engine))

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    schedule_api.reset_state()  # 인메모리 fired/acked 격리
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    schedule_api.reset_state()


def test_settings_round_trip(client: TestClient) -> None:
    # 최초 GET → config 기본값으로 시드
    res = client.get("/schedule/settings")
    assert res.status_code == 200
    body = res.json()
    assert body["enabled"] is True
    assert "poll_interval_sec" in body and "catchup_minutes" in body  # 읽기 전용 노브

    # PUT 부분 갱신
    res = client.put("/schedule/settings", json={"mute_start": "23:30", "lead_minutes": 20})
    assert res.status_code == 200
    body = res.json()
    assert body["mute_start"] == "23:30"
    assert body["lead_minutes"] == 20
    # 미지정 필드 보존
    assert body["checkin_enabled"] is True


def test_disabled_returns_empty(client: TestClient) -> None:
    client.put("/schedule/settings", json={"enabled": False})
    assert client.get("/schedule/due").json() == []
    assert client.get("/schedule/pending").json() == []


def test_checkin_pending_then_ack(client: TestClient) -> None:
    # 체크인 00:00 → 하루 중 언제든 이미 지난 시점 → pending 에 등장
    client.put("/schedule/settings", json={"checkin_time": "00:00", "enabled": True})

    pending = client.get("/schedule/pending").json()
    checkin = [r for r in pending if r["kind"] == "checkin"]
    assert checkin, f"expected a checkin reminder in pending, got {pending}"
    key = checkin[0]["key"]

    # ack → pending 에서 제거
    res = client.post("/schedule/ack", json={"key": key})
    assert res.status_code == 200
    assert key in res.json()["acked"]
    remaining = [r for r in client.get("/schedule/pending").json() if r["key"] == key]
    assert remaining == []


def test_mute_window_suppresses_due(client: TestClient) -> None:
    # 거의 하루 전체(00:00–23:59)를 음소거하면 due 는 비어야 한다(시각 의존 없이 결정적).
    # 단순 toast 억제이므로 pending(앱 내 목록)에는 영향 없다 — 코어 테스트가 커버.
    client.put(
        "/schedule/settings",
        json={"checkin_time": "00:00", "mute_start": "00:00", "mute_end": "23:59"},
    )
    assert client.get("/schedule/due").json() == []
