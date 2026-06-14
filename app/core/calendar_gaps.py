"""캘린더 틈새(빈 시간) 계산 — 순수 도메인 로직 (ADR-022 §다른 일정 읽기).

Google Calendar free/busy 로 읽은 바쁜 구간(busy intervals)을 받아 "지금부터 하루 끝
사이의 빈 시간"을 계산하고, 코치가 능동 제안에 쓸 한국어 힌트 한 줄로 요약한다.

**외부 의존 0** (ADR-012 core 규칙): google API·DB·FastAPI import 없음. busy 구간은
호출부(adapter/pipecat_services)가 google 에서 읽어 ``BusyInterval`` 로 넘긴다. 시각은
모두 로컬 wall-clock naive ``datetime`` (단일 사용자, ADR-002 — "저녁 8시"는 사용자
머신 시간이지 UTC 가 아니다).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class BusyInterval:
    """바쁜 구간 한 칸. ``start`` < ``end`` 를 가정(역전 입력은 merge 단계에서 버려짐)."""

    start: datetime
    end: datetime


def merge_busy(intervals: list[BusyInterval]) -> list[BusyInterval]:
    """겹치거나 맞닿은 바쁜 구간을 병합해 정렬된 목록으로. 0 길이/역전 구간은 버린다."""
    valid = [iv for iv in intervals if iv.start < iv.end]
    valid.sort(key=lambda iv: iv.start)
    merged: list[BusyInterval] = []
    for iv in valid:
        if merged and iv.start <= merged[-1].end:
            last = merged[-1]
            if iv.end > last.end:
                merged[-1] = BusyInterval(last.start, iv.end)
        else:
            merged.append(iv)
    return merged


def free_gaps(
    now: datetime,
    day_end: datetime,
    busy: list[BusyInterval],
    *,
    min_minutes: int = 30,
) -> list[BusyInterval]:
    """``now``~``day_end`` 사이에서 ``min_minutes`` 이상 비어 있는 구간 목록.

    ``day_end`` 가 ``now`` 보다 같거나 이르면(이미 하루 끝 지남) 빈 목록.
    """
    if day_end <= now:
        return []
    threshold = max(0, min_minutes) * 60
    gaps: list[BusyInterval] = []
    cursor = now
    for iv in merge_busy(busy):
        if iv.end <= now:
            continue  # 이미 지난 구간
        if iv.start >= day_end:
            break  # 하루 끝 이후
        gap_start, gap_end = cursor, min(iv.start, day_end)
        if (gap_end - gap_start).total_seconds() >= threshold:
            gaps.append(BusyInterval(gap_start, gap_end))
        if iv.end > cursor:
            cursor = iv.end
        if cursor >= day_end:
            return gaps
    if (day_end - cursor).total_seconds() >= threshold:
        gaps.append(BusyInterval(cursor, day_end))
    return gaps


def _korean_clock(dt: datetime) -> str:
    """``datetime`` → "저녁 8시" / "오전 9시 30분" 같은 한국어 시각 표기."""
    h = dt.hour
    if 5 <= h < 11:
        period = "아침"
    elif 11 <= h < 17:
        period = "낮"
    elif 17 <= h < 22:
        period = "저녁"
    else:
        period = "밤"
    hour12 = h % 12 or 12
    label = f"{period} {hour12}시"
    if dt.minute:
        label += f" {dt.minute}분"
    return label


def summarize_gap(now: datetime, gaps: list[BusyInterval]) -> str | None:
    """틈새 목록을 코치 컨텍스트용 한 줄 한국어 힌트로. 빈 목록이면 None.

    - 지금 비어 있고(첫 틈새가 now 에서 시작) 곧 일정이 있으면: "지금부터 저녁 8시까지 비어 있어요".
    - 지금 바쁘고 이후 틈새가 있으면: "저녁 7시부터 8시까지 비어 있어요".
    하루 끝까지 통으로 빈 경우는 끝 시각으로 마무리한다.
    """
    if not gaps:
        return None
    first = gaps[0]
    # now 와 거의 동시에 시작하면(60초 이내) "지금부터".
    starts_now = (first.start - now).total_seconds() <= 60
    end_label = _korean_clock(first.end)
    if starts_now:
        return f"지금부터 {end_label}까지 비어 있어요"
    return f"{_korean_clock(first.start)}부터 {end_label}까지 비어 있어요"
