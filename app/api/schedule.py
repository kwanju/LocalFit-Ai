"""Phase v4-8 — 능동 알림 스케줄 엔드포인트 (ADR-027).

모델 없는 경량 경로다(ADR-030): 일정만 읽고 toast 발생 여부만 계산한다. 실제 native
toast 와 폴링 타이머는 Tauri 셸의 웹뷰(항상 상주)가 담당하고, 여기서는 "지금 띄울
리마인드"(``GET /schedule/due``)와 "앱 내 배지/누락 목록"(``GET /schedule/pending``)을
계산해 돌려준다. 클릭→세션 라우팅은 사용자가 앱을 여는 경로(트레이/창)에서 pending 을
확인해 진입한다(Windows 데스크탑 toast 는 클릭 라우팅 미지원 — phase 명세 8-3 결정).

스케줄 소스 우선순위(ADR-022/027 fallback):
- 활성 주간 플랜(ADR-024)이 있으면 **오늘 요일에 미완료 PlanDay 가 있을 때만** 운동 알림.
- 플랜이 없으면 **매일**(로컬 fallback) 운동 알림.
- 운동 시각 = ``UserProfile.available_times`` (있으면) 아니면 설정의 ``workout_time``.
- 체크인 알림 = 설정 ``checkin_enabled`` 시 ``checkin_time`` (ADR-023).

상태(발생/확인 키)는 단일 사용자·단일 프로세스라 인메모리로 둔다(ADR-002). 키에 날짜가
들어가 매일 자연 리셋되고, 앱을 완전히 껐다 켜면 인메모리가 비지만 처리 안 된 과거
리마인드는 ``/pending`` 이 스케줄에서 재계산해 다시 보여준다(누락 표시).
"""

from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import NotificationsConfig
from app.core.schedule import (
    KIND_CHECKIN,
    KIND_WORKOUT,
    Reminder,
    ScheduleSlot,
    compute_due,
    parse_hhmm,
    pending,
)
from app.db.engine import get_session
from app.db.repositories import (
    NotificationSettingsRepository,
    PlanRepository,
    UserProfileRepository,
)

router = APIRouter(prefix="/schedule", tags=["schedule"])

# 사용자 대면 문구(한국어, coding-style §7). 시스템 로그는 영어.
_WORKOUT_TITLE = "운동할 시간이에요 💪"
_WORKOUT_BODY = "오늘 계획한 운동을 시작해볼까요?"
_CHECKIN_TITLE = "컨디션 체크인"
_CHECKIN_BODY = "오늘 컨디션을 기록하면 코치가 강도를 맞춰줘요."

# 인메모리 상태(단일 사용자·단일 프로세스, 앱 수명). 날짜가 키에 들어가 매일 리셋.
_fired_keys: set[str] = set()
_acked_keys: set[str] = set()


def reset_state() -> None:
    """테스트용 — 인메모리 상태 초기화."""
    _fired_keys.clear()
    _acked_keys.clear()


def _notif_config(request: Request) -> NotificationsConfig:
    config = getattr(request.app.state, "config", None)
    return config.notifications if config is not None else NotificationsConfig()


def _parse_times(raw: str | None) -> list:
    """``UserProfile.available_times`` (JSON 배열 문자열) → ``time`` 목록(파싱 가능분만)."""
    if not raw:
        return []
    try:
        values = json.loads(raw)
    except (ValueError, TypeError):
        return []
    if not isinstance(values, list):
        return []
    out = [parse_hhmm(v) for v in values if isinstance(v, str)]
    return [t for t in out if t is not None]


async def _is_workout_day(session: AsyncSession, today_weekday: int) -> bool:
    """오늘이 운동일인가. 활성 플랜이 있으면 오늘 요일의 미완료 PlanDay 유무로,
    없으면 매일(로컬 fallback, ADR-027)."""
    plan_repo = PlanRepository(session)
    plan = await plan_repo.get_active()
    if plan is None or plan.id is None:
        return True
    days = await plan_repo.list_days(plan.id)
    return any(d.weekday == today_weekday and not d.completed for d in days)


async def _build_today_slots(
    session: AsyncSession, settings, now: datetime
) -> list[ScheduleSlot]:
    profile = await UserProfileRepository(session).get()
    times = _parse_times(profile.available_times) if profile is not None else []
    if not times:
        default_time = parse_hhmm(settings.workout_time)
        times = [default_time] if default_time is not None else []

    slots: list[ScheduleSlot] = []
    if times and await _is_workout_day(session, now.weekday()):
        for t in times:
            slots.append(ScheduleSlot(KIND_WORKOUT, t, _WORKOUT_TITLE, _WORKOUT_BODY))

    if settings.checkin_enabled:
        checkin_at = parse_hhmm(settings.checkin_time)
        if checkin_at is not None:
            slots.append(ScheduleSlot(KIND_CHECKIN, checkin_at, _CHECKIN_TITLE, _CHECKIN_BODY))
    return slots


class ReminderOut(BaseModel):
    key: str
    kind: str
    title: str
    body: str
    scheduled_for: datetime


def _to_out(r: Reminder) -> ReminderOut:
    return ReminderOut(
        key=r.key, kind=r.kind, title=r.title, body=r.body, scheduled_for=r.scheduled_for
    )


@router.get("/due")
async def get_due(
    request: Request, session: AsyncSession = Depends(get_session)
) -> list[ReminderOut]:
    """지금 toast 로 띄울 리마인드. 폴러(웹뷰)가 호출 → 각 건을 native toast 로 발생.

    반환된 키는 발생 처리(``_fired_keys``)되어 다음 폴링에 중복 toast 되지 않는다.
    설정이 비활성이면 빈 목록.
    """
    cfg = _notif_config(request)
    settings = await NotificationSettingsRepository(session).get_or_create(cfg)
    if not settings.enabled:
        return []

    now = datetime.now()  # 로컬 wall-clock — "오후 6시"는 사용자 머신 시간(ADR-002)
    slots = await _build_today_slots(session, settings, now)
    due = compute_due(
        now,
        slots,
        lead_minutes=settings.lead_minutes,
        mute_start=parse_hhmm(settings.mute_start),
        mute_end=parse_hhmm(settings.mute_end),
        catchup_minutes=cfg.catchup_minutes,
        fired_keys=_fired_keys,
    )
    for r in due:
        _fired_keys.add(r.key)
    return [_to_out(r) for r in due]


@router.get("/pending")
async def get_pending(
    request: Request, session: AsyncSession = Depends(get_session)
) -> list[ReminderOut]:
    """앱 내 배지/리스트 + 앱-오픈 라우팅용 — 오늘 발생 시점이 지났고 아직 처리(ack)
    안 한 리마인드. 음소거·OS 알림 꺼짐과 무관(앱을 열면 항상 보임)."""
    cfg = _notif_config(request)
    settings = await NotificationSettingsRepository(session).get_or_create(cfg)
    if not settings.enabled:
        return []

    now = datetime.now()
    slots = await _build_today_slots(session, settings, now)
    items = pending(now, slots, lead_minutes=settings.lead_minutes, acked_keys=_acked_keys)
    return [_to_out(r) for r in items]


class AckRequest(BaseModel):
    key: str | None = None  # None 이면 현재 pending 전부 확인 처리


@router.post("/ack")
async def ack(
    body: AckRequest, request: Request, session: AsyncSession = Depends(get_session)
) -> dict:
    """리마인드를 처리됨으로 표시(사용자가 세션 시작 또는 닫음). pending 에서 빠진다."""
    if body.key is not None:
        _acked_keys.add(body.key)
        return {"acked": [body.key]}
    # key 미지정 → 현재 pending 전부 ack
    cfg = _notif_config(request)
    settings = await NotificationSettingsRepository(session).get_or_create(cfg)
    now = datetime.now()
    slots = await _build_today_slots(session, settings, now)
    keys = [
        r.key
        for r in pending(now, slots, lead_minutes=settings.lead_minutes, acked_keys=_acked_keys)
    ]
    _acked_keys.update(keys)
    return {"acked": keys}


class SettingsOut(BaseModel):
    enabled: bool
    lead_minutes: int
    workout_time: str
    mute_start: str | None
    mute_end: str | None
    checkin_enabled: bool
    checkin_time: str
    poll_interval_sec: int   # config 전용(읽기 전용) — 폴러가 자기 간격 설정에 사용
    catchup_minutes: int     # config 전용(읽기 전용)


class SettingsUpdate(BaseModel):
    enabled: bool | None = None
    lead_minutes: int | None = None
    workout_time: str | None = None
    mute_start: str | None = None
    mute_end: str | None = None
    checkin_enabled: bool | None = None
    checkin_time: str | None = None


def _settings_out(settings, cfg: NotificationsConfig) -> SettingsOut:
    return SettingsOut(
        enabled=settings.enabled,
        lead_minutes=settings.lead_minutes,
        workout_time=settings.workout_time,
        mute_start=settings.mute_start,
        mute_end=settings.mute_end,
        checkin_enabled=settings.checkin_enabled,
        checkin_time=settings.checkin_time,
        poll_interval_sec=cfg.poll_interval_sec,
        catchup_minutes=cfg.catchup_minutes,
    )


@router.get("/settings")
async def get_settings(
    request: Request, session: AsyncSession = Depends(get_session)
) -> SettingsOut:
    cfg = _notif_config(request)
    settings = await NotificationSettingsRepository(session).get_or_create(cfg)
    return _settings_out(settings, cfg)


@router.put("/settings")
async def update_settings(
    body: SettingsUpdate, request: Request, session: AsyncSession = Depends(get_session)
) -> SettingsOut:
    cfg = _notif_config(request)
    settings = await NotificationSettingsRepository(session).update(
        cfg, **body.model_dump(exclude_unset=True)
    )
    return _settings_out(settings, cfg)
