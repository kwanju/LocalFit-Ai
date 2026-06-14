"""Phase v4-8 — 능동 알림 스케줄 순수 로직 (ADR-027).

운동 시간/체크인 리마인드 시점 계산. **외부 의존 0** (DB·FastAPI·모델 import 금지,
ADR-012) — 슬롯·현재시각·설정만 받아 "지금 띄울 알림"을 계산하는 순수 함수다.
DB 에서 플랜·프로필을 읽어 슬롯을 만드는 부분은 api 계층(`app/api/schedule.py`)이
담당하고, 여기서는 그 슬롯을 시각 기준으로 판정만 한다.

시각은 모두 **로컬 wall-clock**(naive ``datetime``) 기준이다 — "오후 6시"는 사용자
머신의 로컬 시간이지 UTC 가 아니다(단일 사용자, ADR-002). 호출부가 ``datetime.now()``
(naive 로컬)를 넘긴다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

# 알림 종류. "workout"=운동 시간, "checkin"=컨디션 체크인(ADR-023).
KIND_WORKOUT = "workout"
KIND_CHECKIN = "checkin"


@dataclass(frozen=True)
class ScheduleSlot:
    """하루 안의 알림 슬롯 한 칸. ``at`` 은 슬롯의 기준 시각(운동 시작/체크인 시각)."""

    kind: str          # KIND_WORKOUT | KIND_CHECKIN
    at: time           # 로컬 time-of-day
    title: str
    body: str


@dataclass(frozen=True)
class Reminder:
    """판정된 리마인드 1건. ``key`` 는 날짜·종목·시각을 담은 dedup 키라 같은 날 같은
    슬롯은 한 번만 발생한다(폴링이 반복돼도 중복 toast 방지)."""

    key: str
    kind: str
    scheduled_for: datetime   # 슬롯 기준 시각(예: 운동 18:00)
    fire_at: datetime         # 실제 알림 시점(운동 = scheduled_for - lead, 체크인 = scheduled_for)
    title: str
    body: str


def parse_hhmm(value: str | None) -> time | None:
    """"HH:MM" 문자열을 ``time`` 으로. 형식이 어긋나면 ``None`` (방어적 — 사용자 입력)."""
    if not value:
        return None
    parts = value.strip().split(":")
    if len(parts) != 2:
        return None
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return time(hour=hour, minute=minute)


def in_mute_window(now_t: time, start: time | None, end: time | None) -> bool:
    """``now_t`` 가 음소거 시간대 안인가. 한쪽이라도 미설정이면 음소거 없음(False).

    야간 래핑(예: 22:00–07:00)을 처리한다 — start > end 면 자정을 넘는 구간으로 보고
    ``now >= start`` 또는 ``now < end`` 면 음소거. 같은 날 구간(예: 13:00–14:00)은
    ``start <= now < end``. ``start == end`` 는 빈 구간(음소거 없음)으로 본다.
    """
    if start is None or end is None or start == end:
        return False
    if start < end:
        return start <= now_t < end
    # 야간 래핑: [start, 24:00) ∪ [00:00, end)
    return now_t >= start or now_t < end


def reminders_for_day(today: date, slots: list[ScheduleSlot], lead_minutes: int) -> list[Reminder]:
    """그 날의 모든 슬롯을 ``Reminder`` 로 펼친다(판정 전 후보 목록).

    운동 슬롯은 ``lead_minutes`` 만큼 앞당겨 발생(예: 18:00 운동, lead 10 → 17:50 알림).
    체크인은 앞당기지 않는다(시각 자체가 리마인드 시점).
    """
    lead = max(0, lead_minutes)
    out: list[Reminder] = []
    for slot in slots:
        scheduled = datetime.combine(today, slot.at)
        fire_at = scheduled - timedelta(minutes=lead) if slot.kind == KIND_WORKOUT else scheduled
        key = f"{slot.kind}|{today.isoformat()}|{slot.at.strftime('%H:%M')}"
        out.append(
            Reminder(
                key=key,
                kind=slot.kind,
                scheduled_for=scheduled,
                fire_at=fire_at,
                title=slot.title,
                body=slot.body,
            )
        )
    return out


def compute_due(
    now: datetime,
    slots: list[ScheduleSlot],
    *,
    lead_minutes: int,
    mute_start: time | None,
    mute_end: time | None,
    catchup_minutes: int,
    fired_keys: set[str],
) -> list[Reminder]:
    """지금 toast 로 띄워야 할 리마인드. 폴링마다 호출된다.

    규칙:
    - 음소거 시간대면 빈 목록(toast 억제 — 단 앱 내 목록(``pending``)에는 남는다).
    - 이미 발생한 키(``fired_keys``)는 제외(중복 방지).
    - ``fire_at <= now <= fire_at + catchup`` 인 슬롯만 "지금 발생". catchup 창은
      스케줄러가 잠깐 죽었다 살아나거나 폴링 간격을 놓쳐도 따라잡게 한다. 창을 넘긴
      과거 슬롯은 toast 하지 않고 ``pending`` 에서만 보인다(누락 표시).
    """
    if in_mute_window(now.time(), mute_start, mute_end):
        return []
    catchup = timedelta(minutes=max(0, catchup_minutes))
    due: list[Reminder] = []
    for r in reminders_for_day(now.date(), slots, lead_minutes):
        if r.key in fired_keys:
            continue
        if r.fire_at <= now <= r.fire_at + catchup:
            due.append(r)
    return due


def pending(
    now: datetime,
    slots: list[ScheduleSlot],
    *,
    lead_minutes: int,
    acked_keys: set[str],
) -> list[Reminder]:
    """앱 내 배지/리스트 + 앱-오픈 라우팅용. 오늘 슬롯 중 발생 시점이 지났고 아직
    사용자가 처리(ack)하지 않은 것 전부.

    음소거와 무관하다 — 음소거는 toast(팝업)만 억제하고, 앱을 열면 놓친 리마인드를
    볼 수 있어야 한다(ADR-027 안 행복한 경로: OS 알림 꺼짐 → 앱 내 fallback).
    ``fired`` 여부와도 무관 — 토스트가 떴든 안 떴든 처리 전이면 보여준다.
    """
    out: list[Reminder] = []
    for r in reminders_for_day(now.date(), slots, lead_minutes):
        if r.key in acked_keys:
            continue
        if r.fire_at <= now:
            out.append(r)
    return out
