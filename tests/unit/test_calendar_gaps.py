"""캘린더 틈새 계산 순수 로직 테스트 (ADR-022 §9-3)."""

from __future__ import annotations

from datetime import datetime

from app.core.calendar_gaps import BusyInterval, free_gaps, merge_busy, summarize_gap


def _dt(h: int, m: int = 0) -> datetime:
    return datetime(2026, 6, 14, h, m)


def test_merge_overlapping_and_touching() -> None:
    busy = [
        BusyInterval(_dt(10), _dt(11)),
        BusyInterval(_dt(10, 30), _dt(12)),  # overlaps previous
        BusyInterval(_dt(12), _dt(13)),       # touches previous
        BusyInterval(_dt(15), _dt(16)),       # separate
    ]
    merged = merge_busy(busy)
    assert merged == [BusyInterval(_dt(10), _dt(13)), BusyInterval(_dt(15), _dt(16))]


def test_merge_drops_zero_and_reversed() -> None:
    busy = [BusyInterval(_dt(10), _dt(10)), BusyInterval(_dt(12), _dt(11))]
    assert merge_busy(busy) == []


def test_free_gaps_free_now_until_first_event() -> None:
    now = _dt(14)
    day_end = _dt(22)
    busy = [BusyInterval(_dt(16), _dt(17))]
    gaps = free_gaps(now, day_end, busy, min_minutes=30)
    # now→16 (free), 17→22 (free)
    assert gaps[0] == BusyInterval(_dt(14), _dt(16))
    assert gaps[-1] == BusyInterval(_dt(17), _dt(22))


def test_free_gaps_respects_min_minutes() -> None:
    now = _dt(14)
    day_end = _dt(22)
    # 14:00–14:10 sliver before a long meeting → dropped by 30-min threshold
    busy = [BusyInterval(_dt(14, 10), _dt(21, 50))]
    gaps = free_gaps(now, day_end, busy, min_minutes=30)
    assert gaps == []  # both slivers < 30min


def test_free_gaps_empty_when_day_end_past() -> None:
    assert free_gaps(_dt(22), _dt(20), []) == []


def test_summarize_gap_starts_now() -> None:
    now = _dt(14)
    gaps = [BusyInterval(_dt(14), _dt(20))]
    assert summarize_gap(now, gaps) == "지금부터 저녁 8시까지 비어 있어요"


def test_summarize_gap_later_window() -> None:
    now = _dt(14)
    gaps = [BusyInterval(_dt(19), _dt(20, 30))]
    assert summarize_gap(now, gaps) == "저녁 7시부터 저녁 8시 30분까지 비어 있어요"


def test_summarize_gap_none_when_empty() -> None:
    assert summarize_gap(_dt(14), []) is None
