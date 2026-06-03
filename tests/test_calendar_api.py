"""Integration tests for GET /api/calendar (ADR-019, ADR-020).

Uses an in-memory SQLite DB patched into app.db.engine so no config.yaml is needed.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

import app.db.engine as db_engine_module
from app.db.models import EXERCISE_SEED, Exercise, WorkoutSession
from app.main import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def test_db():
    """Spin up an in-memory SQLite DB, patch app.db.engine, and clean up."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    import app.db.models  # noqa: F401 — register SQLModel metadata

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Seed exercises
    async with factory() as db:
        for data in EXERCISE_SEED:
            db.add(Exercise(**data))
        await db.commit()

    # Patch the global engine/factory
    _orig_engine = db_engine_module._engine
    _orig_factory = db_engine_module._session_factory
    db_engine_module._engine = engine
    db_engine_module._session_factory = factory

    yield engine, factory

    db_engine_module._engine = _orig_engine
    db_engine_module._session_factory = _orig_factory
    await engine.dispose()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_calendar_empty_db(test_db) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/calendar")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_calendar_with_completed_session(test_db) -> None:
    _engine, factory = test_db

    async with factory() as db:
        ws = WorkoutSession(
            mode="c2c",
            started_at=datetime.now(UTC),
            ended_at=datetime.now(UTC),
        )
        db.add(ws)
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/calendar")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["level"] == 0      # no set logs → volume 0 → level 0
    assert data[0]["volume"] == 0.0
    assert len(data[0]["sessions"]) == 1


@pytest.mark.asyncio
async def test_calendar_date_range_filter(test_db) -> None:
    _engine, factory = test_db

    async with factory() as db:
        # Add two sessions on different dates (past)
        old = WorkoutSession(mode="c2c", started_at=datetime(2025, 1, 1, tzinfo=UTC))
        recent = WorkoutSession(mode="c2c", started_at=datetime.now(UTC))
        db.add_all([old, recent])
        await db.commit()

    # Request only the recent year
    today_str = datetime.now(UTC).strftime("%Y-%m-%d")
    year_str = str(datetime.now(UTC).year)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/api/calendar?from={year_str}-01-01&to={today_str}")

    assert resp.status_code == 200
    data = resp.json()
    # Only the recent session should appear (2025 session filtered out)
    assert len(data) == 1


@pytest.mark.asyncio
async def test_calendar_response_schema(test_db) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/calendar")
    assert resp.status_code == 200
    # empty list is valid
    assert isinstance(resp.json(), list)
