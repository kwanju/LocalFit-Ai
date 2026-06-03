"""Tests that CoachContextBuilder injects calendar signals when provided (ADR-013, ADR-020)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pytest

from app.core.coach_context import CalendarSignals, CoachContextBuilder


# ---------------------------------------------------------------------------
# Minimal protocol-compliant stubs
# ---------------------------------------------------------------------------


class _EmptyRepo:
    async def get(self) -> None:
        return None

    async def get_recent(self, limit: int = 10) -> list:
        return []

    async def get_by_session(self, session_id: int) -> list:
        return []

    async def list_all(self) -> list:
        return []


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_context_without_calendar_signals() -> None:
    """When calendar_signals_fn is None, calendar sections are omitted."""
    builder = CoachContextBuilder(
        profile_repo=_EmptyRepo(),  # type: ignore[arg-type]
        session_repo=_EmptyRepo(),  # type: ignore[arg-type]
        set_repo=_EmptyRepo(),  # type: ignore[arg-type]
        condition_repo=_EmptyRepo(),  # type: ignore[arg-type]
        routine_repo=_EmptyRepo(),  # type: ignore[arg-type]
        calendar_signals_fn=None,
    )
    ctx = await builder.build()
    assert "주간 패턴" not in ctx
    assert "운동별 마지막" not in ctx
    assert "휴식 streak" not in ctx


@pytest.mark.asyncio
async def test_context_with_weekly_pattern() -> None:
    """weekly_pattern is injected into the context string."""

    async def _signals() -> CalendarSignals:
        return CalendarSignals(weekly_pattern="월·수·금 주 3회")

    builder = CoachContextBuilder(
        profile_repo=_EmptyRepo(),  # type: ignore[arg-type]
        session_repo=_EmptyRepo(),  # type: ignore[arg-type]
        set_repo=_EmptyRepo(),  # type: ignore[arg-type]
        condition_repo=_EmptyRepo(),  # type: ignore[arg-type]
        routine_repo=_EmptyRepo(),  # type: ignore[arg-type]
        calendar_signals_fn=_signals,
    )
    ctx = await builder.build()
    assert "주간 패턴" in ctx
    assert "월·수·금 주 3회" in ctx


@pytest.mark.asyncio
async def test_context_with_last_exercise() -> None:
    """last_exercise dict is formatted and injected."""

    async def _signals() -> CalendarSignals:
        return CalendarSignals(last_exercise={"푸시업": "5일 전", "풀업": "어제"})

    builder = CoachContextBuilder(
        profile_repo=_EmptyRepo(),  # type: ignore[arg-type]
        session_repo=_EmptyRepo(),  # type: ignore[arg-type]
        set_repo=_EmptyRepo(),  # type: ignore[arg-type]
        condition_repo=_EmptyRepo(),  # type: ignore[arg-type]
        routine_repo=_EmptyRepo(),  # type: ignore[arg-type]
        calendar_signals_fn=_signals,
    )
    ctx = await builder.build()
    assert "운동별 마지막" in ctx
    assert "푸시업" in ctx
    assert "5일 전" in ctx


@pytest.mark.asyncio
async def test_context_with_rest_streak() -> None:
    """rest_streak_days ≥ 2 produces a streak notice."""

    async def _signals() -> CalendarSignals:
        return CalendarSignals(rest_streak_days=3)

    builder = CoachContextBuilder(
        profile_repo=_EmptyRepo(),  # type: ignore[arg-type]
        session_repo=_EmptyRepo(),  # type: ignore[arg-type]
        set_repo=_EmptyRepo(),  # type: ignore[arg-type]
        condition_repo=_EmptyRepo(),  # type: ignore[arg-type]
        routine_repo=_EmptyRepo(),  # type: ignore[arg-type]
        calendar_signals_fn=_signals,
    )
    ctx = await builder.build()
    assert "휴식 streak" in ctx
    assert "3일" in ctx


@pytest.mark.asyncio
async def test_context_rest_streak_below_threshold_omitted() -> None:
    """rest_streak_days < 2 is not mentioned (noise reduction)."""

    async def _signals() -> CalendarSignals:
        return CalendarSignals(rest_streak_days=1)

    builder = CoachContextBuilder(
        profile_repo=_EmptyRepo(),  # type: ignore[arg-type]
        session_repo=_EmptyRepo(),  # type: ignore[arg-type]
        set_repo=_EmptyRepo(),  # type: ignore[arg-type]
        condition_repo=_EmptyRepo(),  # type: ignore[arg-type]
        routine_repo=_EmptyRepo(),  # type: ignore[arg-type]
        calendar_signals_fn=_signals,
    )
    ctx = await builder.build()
    assert "휴식 streak" not in ctx


@pytest.mark.asyncio
async def test_context_signals_error_is_swallowed() -> None:
    """A broken calendar_signals_fn must not crash the context builder."""

    async def _broken_signals() -> CalendarSignals:
        raise RuntimeError("DB is down")

    builder = CoachContextBuilder(
        profile_repo=_EmptyRepo(),  # type: ignore[arg-type]
        session_repo=_EmptyRepo(),  # type: ignore[arg-type]
        set_repo=_EmptyRepo(),  # type: ignore[arg-type]
        condition_repo=_EmptyRepo(),  # type: ignore[arg-type]
        routine_repo=_EmptyRepo(),  # type: ignore[arg-type]
        calendar_signals_fn=_broken_signals,
    )
    ctx = await builder.build()
    # Must still return a non-empty string
    assert isinstance(ctx, str)
    assert len(ctx) > 0
