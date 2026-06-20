"""Google Calendar 오케스트레이션 (ADR-022) — pipecat_services 계층.

adapters(gcal client/oauth) + core(calendar_gaps 순수 틈새 계산) + db(PlanRepository)를
묶는 자리다(ADR-012 §의존 방향 — pipecat_services 는 셋 다 import 가능). api(`gcal.py`)와
ws_voice 의 캘린더 동기 commit 콜백, 스케줄러(`schedule.py`)·컨텍스트 빌더가 공유한다.

설계 원칙(ADR-022 안 행복한 경로 / 회고 원칙 1):
- **미연동/오프라인/Google 장애는 예외가 아니라 정상 분기다.** 모든 공개 메서드는 실패 시
  None/빈 결과로 degrade 하고 ``logger`` 로 남긴다 — 캘린더 기능만 죽고 코칭은 계속.
- google 호출은 동기(blocking)라 ``asyncio.to_thread`` 로 감싼다.
"""

from __future__ import annotations

import asyncio
import time as _time
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from loguru import logger

from app.config import GoogleCalendarConfig
from app.core.calendar_gaps import BusyInterval, free_gaps, summarize_gap
from app.core.schedule import parse_hhmm
from app.db.engine import create_db_session
from app.db.repositories import PlanRepository, UserProfileRepository


@dataclass(frozen=True)
class ProposedEvent:
    """등록 후보 운동 이벤트(미리보기/확답 게이트용). 아직 캘린더에 쓰이지 않음."""

    exercise: str
    start: datetime
    end: datetime
    summary: str


@dataclass(frozen=True)
class RegisterResult:
    created: int
    skipped: int
    events: list[ProposedEvent]


# 스케줄러가 60초마다 폴링하므로 google 을 매번 때리지 않게 today_workout_times 결과를
# 짧게 캐시한다(단일 사용자·단일 프로세스). 날짜가 바뀌면 자연 무효화.
_workout_times_cache: dict[str, tuple[float, list[time]]] = {}
_WORKOUT_TIMES_TTL_SEC = 120.0

# 등록/생성 이벤트의 최소 길이(분). config 값이 더 작아도 캘린더에 0분 이벤트가 안 생기게.
MIN_EVENT_DURATION_MIN = 5


class CalendarSyncService:
    def __init__(self, config: GoogleCalendarConfig) -> None:
        self._config = config

    # ── 연결 ────────────────────────────────────────────────────────────
    async def is_connected(self) -> bool:
        if not self._config.enabled:
            return False
        from app.adapters.calendar import oauth

        return await asyncio.to_thread(oauth.is_connected)

    async def _client(self):
        """연결된 ``GoogleCalendarClient`` 또는 None(미연동/비활성)."""
        if not self._config.enabled:
            return None
        from app.adapters.calendar.client import GoogleCalendarClient

        return await asyncio.to_thread(
            GoogleCalendarClient.connect, self._config.calendar_id
        )

    # ── 틈새 추천 (§9-3) ────────────────────────────────────────────────
    async def today_gap_hint(self, now: datetime | None = None) -> str | None:
        """오늘 ``now``~``gap_day_end`` 사이 빈 시간을 읽어 코치용 한 줄 힌트. 실패/미연동 None."""
        now = now or datetime.now()
        client = await self._client()
        if client is None:
            return None
        day_end_t = parse_hhmm(self._config.gap_day_end) or time(22, 0)
        day_end = datetime.combine(now.date(), day_end_t)
        if day_end <= now:
            return None
        try:
            raw = await asyncio.to_thread(client.list_busy, now, day_end)
        except Exception as e:  # noqa: BLE001 — 오프라인/쿼터 → degrade
            logger.error("calendar free/busy read failed (gap hint skipped): {}", e)
            return None
        busy = [BusyInterval(s, e) for s, e in raw]
        gaps = free_gaps(now, day_end, busy, min_minutes=self._config.gap_min_minutes)
        return summarize_gap(now, gaps)

    # ── 스케줄러 소스 (§9-4) ────────────────────────────────────────────
    async def today_workout_times(self, now: datetime | None = None) -> list[time] | None:
        """오늘 캘린더에 잡힌 운동 이벤트의 시작 시각 목록. **미연동이면 None**(→ 호출부
        로컬 fallback). 연동됐지만 오늘 이벤트가 없으면 빈 목록([]).

        60초 폴링 대비 짧은 TTL 캐시를 둔다(google 과부하 방지).
        """
        now = now or datetime.now()
        cache_key = now.date().isoformat()
        cached = _workout_times_cache.get(cache_key)
        if cached is not None and (_time.monotonic() - cached[0]) < _WORKOUT_TIMES_TTL_SEC:
            return list(cached[1])

        client = await self._client()
        if client is None:
            return None  # 미연동 → 로컬 스케줄 fallback
        day_start = datetime.combine(now.date(), time(0, 0))
        day_end = day_start + timedelta(days=1)
        try:
            events = await asyncio.to_thread(client.list_workout_events, day_start, day_end)
        except Exception as e:  # noqa: BLE001 — 오프라인/쿼터 → fallback
            logger.error("calendar workout-events read failed (local fallback): {}", e)
            return None
        times = sorted({ev.start.time().replace(second=0, microsecond=0) for ev in events})
        _workout_times_cache[cache_key] = (_time.monotonic(), times)
        return times

    # ── 경량 CRUD (ADR-034): 보기/생성/삭제 ────────────────────────────
    async def list_events(self, time_min: datetime, time_max: datetime) -> list:
        """``time_min``~``time_max`` 의 전체 일정. 미연동/오류 → 빈 목록(degrade)."""
        client = await self._client()
        if client is None:
            return []
        try:
            return await asyncio.to_thread(client.list_events, time_min, time_max)
        except Exception as e:  # noqa: BLE001 — 오프라인/쿼터 → 빈 목록 degrade
            logger.error("calendar list_events failed (empty list): {}", e)
            return []

    async def create_event(
        self, summary: str, start: datetime, duration_min: int
    ) -> str | None:
        """사용자가 직접 잡는 일정 생성 → event id. 미연동/오류 → None(degrade).

        사용자 명시 액션이라 즉시 쓴다(운동 플랜 등록의 확답 게이트와 별개 — ADR-034).
        """
        client = await self._client()
        if client is None:
            return None
        end = start + timedelta(minutes=max(MIN_EVENT_DURATION_MIN, duration_min))
        try:
            return await asyncio.to_thread(client.insert_event, start, end, summary)
        except Exception as e:  # noqa: BLE001
            logger.error("calendar create_event failed: {}", e)
            return None

    async def delete_event(self, event_id: str) -> bool:
        """일정 삭제. 미연동/오류 → False(degrade), 성공 → True."""
        client = await self._client()
        if client is None:
            return False
        try:
            await asyncio.to_thread(client.delete_event, event_id)
            return True
        except Exception as e:  # noqa: BLE001
            logger.error("calendar delete_event failed ({}): {}", event_id, e)
            return False

    # ── 등록 (§9-2, 확답 게이트) ───────────────────────────────────────
    async def _default_workout_time(self) -> time:
        """등록 이벤트 시각 = profile.available_times[0] 있으면 그것, 없으면 18:00."""
        try:
            async with create_db_session() as db:
                profile = await UserProfileRepository(db).get()
        except Exception:  # noqa: BLE001 — best-effort
            profile = None
        if profile is not None:
            import json

            try:
                values = json.loads(profile.available_times)
                if isinstance(values, list):
                    for v in values:
                        t = parse_hhmm(v) if isinstance(v, str) else None
                        if t is not None:
                            return t
            except (ValueError, TypeError):
                pass
        return time(18, 0)

    async def preview_plan_events(self, now: datetime | None = None) -> list[ProposedEvent]:
        """활성 주간 플랜(ADR-024)의 일자 분배 → 등록 후보 이벤트. **쓰지 않는다**.

        오늘 이후의 미완료 PlanDay 만 대상(과거 날짜·완료 칸 제외). 플랜 없으면 빈 목록.
        """
        now = now or datetime.now()
        async with create_db_session() as db:
            repo = PlanRepository(db)
            plan = await repo.get_active()
            if plan is None or plan.id is None:
                return []
            days = await repo.list_days(plan.id)
            week_start = plan.week_start
        at = await self._default_workout_time()
        duration = timedelta(minutes=max(MIN_EVENT_DURATION_MIN, self._config.event_duration_min))
        out: list[ProposedEvent] = []
        for d in days:
            if d.completed:
                continue
            event_date = week_start + timedelta(days=d.weekday)
            start = datetime.combine(event_date, at)
            if start < now:
                continue  # 과거에 이벤트를 만들지 않음
            out.append(
                ProposedEvent(
                    exercise=d.exercise,
                    start=start,
                    end=start + duration,
                    summary=f"{self._config.workout_summary} · {d.exercise}",
                )
            )
        out.sort(key=lambda e: e.start)
        return out

    async def register_plan_events(self, now: datetime | None = None) -> RegisterResult:
        """미리본 이벤트를 실제 캘린더에 등록. **확답 게이트 통과 후에만** 호출되어야 한다
        (api 의 confirm 플래그 또는 ws_voice 의 ConfirmRule). 미연동이면 빈 결과."""
        proposed = await self.preview_plan_events(now=now)
        if not proposed:
            return RegisterResult(created=0, skipped=0, events=[])
        client = await self._client()
        if client is None:
            logger.warning("register_plan_events: not connected — nothing written")
            return RegisterResult(created=0, skipped=len(proposed), events=[])
        created: list[ProposedEvent] = []
        for ev in proposed:
            try:
                await asyncio.to_thread(
                    client.insert_workout_event, ev.start, ev.end, ev.summary, ev.exercise
                )
                created.append(ev)
            except Exception as e:  # noqa: BLE001 — 개별 실패는 건너뛰고 계속(부분 성공)
                logger.error("calendar event insert failed ({} {}): {}", ev.exercise, ev.start, e)
        # 등록 후 스케줄러 캐시 무효화 — 새 이벤트가 곧바로 알림 소스에 반영되게.
        _workout_times_cache.clear()
        logger.info("calendar register: {}/{} events created", len(created), len(proposed))
        return RegisterResult(
            created=len(created), skipped=len(proposed) - len(created), events=created
        )
