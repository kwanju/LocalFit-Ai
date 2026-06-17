"""Google Calendar 연동 — 동기 서비스 + API (ADR-022, phase v4-9).

외부 Google API 는 전부 mock 한다(GPU·네트워크 불필요). in-memory SQLite 로 활성 주간
플랜을 만들어 등록 미리보기/등록 흐름을 검증한다. 핵심 회귀 가드:
  * 확답(confirm) 없는 등록 요청은 거부(400) — 자동 등록 금지(ADR-022/013).
  * 미연동이면 등록 0건으로 graceful degrade(코칭 영향 없음, 안 행복한 경로).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

import app.db.engine as db_engine_module
import app.pipecat_services.calendar_sync as sync_mod
from app.config import GoogleCalendarConfig
from app.core.plan import PlanGoalSpec
from app.db.repositories import PlanRepository
from app.main import app
from app.pipecat_services.calendar_sync import CalendarSyncService


@pytest.fixture
async def test_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    import app.db.models  # noqa: F401 — register metadata

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    _orig_engine = db_engine_module._engine
    _orig_factory = db_engine_module._session_factory
    db_engine_module._engine = engine
    db_engine_module._session_factory = factory
    sync_mod._workout_times_cache.clear()
    yield engine, factory
    db_engine_module._engine = _orig_engine
    db_engine_module._session_factory = _orig_factory
    await engine.dispose()


class _FakeClient:
    """GoogleCalendarClient 대역 — 네트워크 없이 동작 기록만."""

    def __init__(self) -> None:
        self.inserted: list[tuple] = []
        self.busy: list[tuple[datetime, datetime]] = []
        self.workout_starts: list[datetime] = []
        self.inserted_plain: list[tuple] = []
        self.deleted: list[str] = []
        self.events: list = []

    def insert_workout_event(self, start, end, summary, description=None) -> str:
        self.inserted.append((start, end, summary, description))
        return f"evt-{len(self.inserted)}"

    def list_busy(self, time_min, time_max):
        return self.busy

    def list_workout_events(self, time_min, time_max):
        from app.adapters.calendar.client import WorkoutEvent

        return [WorkoutEvent(event_id="x", start=s, summary="운동") for s in self.workout_starts]

    def list_events(self, time_min, time_max):
        return self.events

    def insert_event(self, start, end, summary) -> str:
        self.inserted_plain.append((start, end, summary))
        return f"plain-{len(self.inserted_plain)}"

    def delete_event(self, event_id) -> None:
        self.deleted.append(event_id)


async def _make_active_plan() -> None:
    """이번 주 시작(today)으로 활성 플랜 생성 — 모든 PlanDay 가 today 이후가 되게."""
    async with db_engine_module._session_factory() as db:
        await PlanRepository(db).create_plan(
            [PlanGoalSpec(exercise="푸시업", target_count=2, reps=10)],
            week_start=date.today(),
        )


# ── 서비스: 미리보기/등록 ────────────────────────────────────────────────


async def test_preview_builds_events_from_active_plan(test_db) -> None:
    await _make_active_plan()
    svc = CalendarSyncService(GoogleCalendarConfig())
    now = datetime.combine(date.today(), time(0, 1))
    events = await svc.preview_plan_events(now=now)
    assert len(events) == 2  # distribute_weekdays(2) → 2칸, 둘 다 미래
    assert all(e.exercise == "푸시업" for e in events)
    assert all(e.start > now for e in events)
    assert events[0].end - events[0].start == timedelta(minutes=30)


async def test_preview_empty_without_plan(test_db) -> None:
    svc = CalendarSyncService(GoogleCalendarConfig())
    assert await svc.preview_plan_events() == []


async def test_register_inserts_when_connected(test_db, monkeypatch) -> None:
    await _make_active_plan()
    fake = _FakeClient()

    async def _fake_client(self):
        return fake

    monkeypatch.setattr(CalendarSyncService, "_client", _fake_client)
    svc = CalendarSyncService(GoogleCalendarConfig())
    now = datetime.combine(date.today(), time(0, 1))
    result = await svc.register_plan_events(now=now)
    assert result.created == 2
    assert len(fake.inserted) == 2


async def test_register_degrades_when_not_connected(test_db, monkeypatch) -> None:
    await _make_active_plan()

    async def _no_client(self):
        return None

    monkeypatch.setattr(CalendarSyncService, "_client", _no_client)
    svc = CalendarSyncService(GoogleCalendarConfig())
    now = datetime.combine(date.today(), time(0, 1))
    result = await svc.register_plan_events(now=now)
    assert result.created == 0  # 미연동 → 등록 0, 예외 없이 degrade


async def test_today_workout_times_none_when_not_connected(test_db, monkeypatch) -> None:
    async def _no_client(self):
        return None

    monkeypatch.setattr(CalendarSyncService, "_client", _no_client)
    svc = CalendarSyncService(GoogleCalendarConfig())
    # None → schedule.py 가 로컬 fallback 으로 degrade(§9-4).
    assert await svc.today_workout_times() is None


async def test_today_gap_hint_from_busy(test_db, monkeypatch) -> None:
    fake = _FakeClient()
    now = datetime(2026, 6, 14, 14, 0)
    fake.busy = [(datetime(2026, 6, 14, 16, 0), datetime(2026, 6, 14, 17, 0))]

    async def _fake_client(self):
        return fake

    monkeypatch.setattr(CalendarSyncService, "_client", _fake_client)
    svc = CalendarSyncService(GoogleCalendarConfig())
    hint = await svc.today_gap_hint(now=now)
    assert hint == "지금부터 낮 4시까지 비어 있어요"


# ── 경량 CRUD: 보기/생성/삭제 (ADR-034) ───────────────────────────────────


async def test_list_events_returns_when_connected(test_db, monkeypatch) -> None:
    from app.adapters.calendar.client import CalEvent

    fake = _FakeClient()
    fake.events = [
        CalEvent(
            event_id="a",
            summary="헬스장",
            start=datetime(2026, 6, 17, 18, 0),
            end=datetime(2026, 6, 17, 19, 0),
            all_day=False,
        )
    ]

    async def _fake_client(self):
        return fake

    monkeypatch.setattr(CalendarSyncService, "_client", _fake_client)
    svc = CalendarSyncService(GoogleCalendarConfig())
    out = await svc.list_events(datetime(2026, 6, 17), datetime(2026, 6, 24))
    assert len(out) == 1
    assert out[0].summary == "헬스장"


async def test_list_events_empty_when_not_connected(test_db, monkeypatch) -> None:
    async def _no_client(self):
        return None

    monkeypatch.setattr(CalendarSyncService, "_client", _no_client)
    svc = CalendarSyncService(GoogleCalendarConfig())
    assert await svc.list_events(datetime(2026, 6, 17), datetime(2026, 6, 24)) == []


async def test_create_and_delete_event(test_db, monkeypatch) -> None:
    fake = _FakeClient()

    async def _fake_client(self):
        return fake

    monkeypatch.setattr(CalendarSyncService, "_client", _fake_client)
    svc = CalendarSyncService(GoogleCalendarConfig())
    eid = await svc.create_event("헬스장", datetime(2026, 6, 18, 18, 0), 45)
    assert eid == "plain-1"
    assert fake.inserted_plain[0][2] == "헬스장"
    assert await svc.delete_event(eid) is True
    assert fake.deleted == ["plain-1"]


async def test_create_event_none_when_not_connected(test_db, monkeypatch) -> None:
    async def _no_client(self):
        return None

    monkeypatch.setattr(CalendarSyncService, "_client", _no_client)
    svc = CalendarSyncService(GoogleCalendarConfig())
    assert await svc.create_event("x", datetime(2026, 6, 18, 18, 0), 30) is None
    assert await svc.delete_event("x") is False


async def test_events_endpoint_degrades_when_not_connected(test_db, monkeypatch) -> None:
    """미연동: events=[] + connected=false (UI 가 연동 안내로 degrade)."""

    async def _not_connected(self):
        return False

    monkeypatch.setattr(CalendarSyncService, "is_connected", _not_connected)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/gcal/events?from=2026-06-17T00:00:00&to=2026-06-24T00:00:00")
    assert resp.status_code == 200
    body = resp.json()
    assert body["connected"] is False
    assert body["events"] == []


async def test_events_endpoint_rejects_bad_dates(test_db) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/gcal/events?from=notadate&to=alsobad")
    assert resp.status_code == 400


async def test_create_event_endpoint_requires_summary(test_db) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/gcal/events", json={"summary": "  ", "start": "2026-06-18T18:00:00"}
        )
    assert resp.status_code == 400


# ── API: 확답 게이트 ──────────────────────────────────────────────────────


async def test_register_endpoint_requires_confirm(test_db) -> None:
    """회귀 가드: confirm 없는 등록 요청은 400 — 동의 없이는 미등록(ADR-022/013)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/gcal/plan/register", json={"confirm": False})
    assert resp.status_code == 400


async def test_status_endpoint_reports_connection(test_db, monkeypatch) -> None:
    async def _connected(self):
        return True

    monkeypatch.setattr(CalendarSyncService, "is_connected", _connected)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/gcal/status")
    assert resp.status_code == 200
    assert resp.json()["connected"] is True
