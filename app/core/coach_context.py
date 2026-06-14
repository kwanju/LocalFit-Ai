"""CoachContextBuilder — composes a 700-char natural-language context string
for every LLM call (ADR-013 §컨텍스트 빌더).

Pure domain code (ADR-012): repositories are injected, no Pipecat/FastAPI/
instructor imports here. Calendar-derived signals (weekly pattern, per-exercise
last performed, rest streak) are stubbed in phase 5 and wired up in phase 8 via
``app.core.calendar_metrics``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from loguru import logger

from app.core.plan import summarize_progress

_MAX_CONTEXT_CHARS: int = 700

# ADR-028: 기준선이 이 일수 이상 지나면 재평가(재측정 대화)를 권하는 힌트를 주입한다.
# (사용자의 "너무 쉬움/어려움" 피드백 트리거는 프롬프트가 직접 처리 — 시간 트리거가 이쪽.)
_BASELINE_REASSESS_DAYS: int = 28

# 시간(초) 기준 종목 — 기준선 metric 이 duration_sec 이고, 시드 표기 단위가 "초".
_TIMER_EXERCISES: frozenset[str] = frozenset({"플랭크"})


class _ProfileRepo(Protocol):
    async def get(self): ...


class _SessionRepo(Protocol):
    async def get_recent(self, limit: int = 10) -> list: ...


class _SetLogRepo(Protocol):
    async def get_by_session(self, session_id: int) -> list: ...


class _ConditionRepo(Protocol):
    async def latest(self): ...


class _RoutineRepo(Protocol):
    async def list_all(self) -> list: ...


class _MemoryRepo(Protocol):
    async def get_constraints(self) -> list: ...
    async def recent_facts(self, limit: int = 10) -> list: ...
    async def get_baseline(self) -> list: ...


class _PlanRepo(Protocol):
    async def get_active(self): ...
    async def progress(self, plan_id: int) -> list: ...


def _time_of_day(now: datetime) -> str:
    h = now.hour
    if 5 <= h < 11:
        return "아침"
    if 11 <= h < 17:
        return "낮"
    if 17 <= h < 22:
        return "저녁"
    return "새벽"


def _profile_summary(profile) -> str:
    if profile is None:
        return "사용자 프로필 없음(온보딩 전)"
    parts: list[str] = []
    if profile.age:
        parts.append(f"{profile.age}세")
    level = getattr(profile, "fitness_level", None)
    if level is not None:
        parts.append(str(level.value if hasattr(level, "value") else level))
    if profile.goal:
        parts.append(f"목표 '{profile.goal}'")
    return f"사용자: {', '.join(parts)}" if parts else "사용자 프로필 미입력"


def _routine_summary(routines) -> str:
    if not routines:
        return "활성 루틴 없음"
    names = ", ".join(r.name for r in routines[:3])
    return f"활성 루틴: {names}"


def _recent_sessions_summary(sessions) -> str:
    """Summarise recent EFFECTIVE sessions (set_log이 1개 이상 있는 세션만).

    필터는 호출자가 미리 적용 — 빈 리스트는 신규 사용자로 취급한다.
    """
    if not sessions:
        return "신규 사용자 (운동 기록 없음)"
    return f"최근 세션 {len(sessions)}회 (가장 최근 {sessions[0].started_at:%m/%d %H시})"


@dataclass
class CalendarSignals:
    """Calendar-derived signals injected into the coach context.

    ``weekly_pattern`` / ``last_exercise`` / ``rest_streak_days`` come from the
    LOCAL ADR-020 workout heatmap (``app.core.calendar_metrics``). ``free_gap_hint``
    comes from a DIFFERENT source — the external Google Calendar free/busy read
    (ADR-022 §9-3) — and is kept as a **separate field** so the two are never
    conflated (phase-9 명세 §9-3).
    """

    weekly_pattern: str | None = None       # e.g. "월·수·금 주 3회"  (ADR-020 히트맵)
    last_exercise: dict[str, str] | None = None  # e.g. {"푸시업": "5일 전"}  (ADR-020)
    rest_streak_days: int = 0               # (ADR-020 히트맵)
    # ADR-022 gcal 틈새. e.g. "지금부터 저녁 8시까지 비어 있어요"
    free_gap_hint: str | None = None


_MAX_RECENT_FACTS: int = 5


@dataclass
class CoachContextBuilder:
    profile_repo: _ProfileRepo
    session_repo: _SessionRepo
    set_repo: _SetLogRepo
    condition_repo: _ConditionRepo
    routine_repo: _RoutineRepo
    calendar_signals_fn: object | None = None   # async () -> CalendarSignals; phase-8 wires it
    memory_repo: _MemoryRepo | None = None      # ADR-025; phase-2 wires it
    plan_repo: _PlanRepo | None = None          # ADR-024; phase-4 wires it

    async def build(self, *, recent_sessions: int = 5, now: datetime | None = None) -> str:
        now = now or datetime.now()
        profile = await self.profile_repo.get()
        # 연결만 하고 운동 안 한 세션(SetLog 없음)은 LLM 컨텍스트에서 제외 — 신규 사용자
        # 시나리오. 효과 세션 계산은 첫-세션 판정과 공유한다(ADR-028).
        sessions = await compute_effective_sessions(
            self.session_repo, self.set_repo, recent_sessions=recent_sessions
        )
        routines = await self.routine_repo.list_all()

        latest_condition = await self._latest_condition()

        signals = await self._calendar_signals()

        # 1층 부상/제약 — 안전 직결. cap 면제로 항상 전량 주입(ADR-025).
        safety_block = await self._safety_block()

        # ADR-028 첫 체력검증 — 기준선·기록 모두 없으면 대화형 검증 흐름을 지시한다.
        baselines = await self._get_baselines()
        first_session_note = (
            self._first_session_block(profile) if (not sessions and not baselines) else None
        )

        parts: list[str] = [_profile_summary(profile)]
        if first_session_note:
            # 첫 세션 지시는 가장 앞에 둬 cap(꼬리 절단)에서 살아남게 한다.
            parts.append(first_session_note)
        parts.extend(
            [
                _routine_summary(routines),
                _recent_sessions_summary(sessions),
            ]
        )
        # 기준선이 오래됐으면 재평가(재측정) 권유 힌트 (ADR-028 N주 트리거).
        if baselines and not first_session_note:
            stale = _baseline_reassess_hint(baselines)
            if stale:
                parts.append(stale)
        if latest_condition:
            parts.append(latest_condition)
        # 주간 플랜·진척 (ADR-024) — 목표가 있으면 "이번 주 목표: 푸시업 1/3회" 주입.
        plan_summary = await self._plan_summary()
        if plan_summary:
            parts.append(plan_summary)
        if signals.weekly_pattern:
            parts.append(f"주간 패턴: {signals.weekly_pattern}")
        if signals.last_exercise:
            last_str = ", ".join(f"{k} {v}" for k, v in signals.last_exercise.items())
            parts.append(f"운동별 마지막: {last_str}")
        if signals.rest_streak_days >= 2:
            parts.append(f"휴식 streak {signals.rest_streak_days}일")
        # ADR-022 §9-3: 외부 Google Calendar 틈새 — 히트맵 신호와 별도 필드(혼동 방지).
        if signals.free_gap_hint:
            parts.append(f"오늘 빈 시간: {signals.free_gap_hint}")
        parts.append(f"현재 {_time_of_day(now)} {now.hour}시")
        # 2층 자유텍스트 메모 — 마지막에 배치해 cap 초과 시 가장 먼저 잘리게 한다.
        memo = await self._recent_memo()
        if memo:
            parts.append(memo)

        # cap 은 비-안전 본문(rest)에만 적용. 부상/제약은 예산 밖(전량 보장).
        rest = " / ".join(parts)
        if len(rest) > _MAX_CONTEXT_CHARS:
            rest = rest[: _MAX_CONTEXT_CHARS - 1] + "…"

        if safety_block:
            return f"{safety_block} / {rest}"
        return rest

    async def _latest_condition(self) -> str | None:
        """가장 최근 자가보고 체크인을 한 줄로(ADR-023). 피로도+근육통+메모 요약.

        세션 연결 여부와 무관하게 ``latest()`` 를 쓰므로 세션 전 체크인(session_id=None)도
        코치가 본다. 강도 조절 *제안*의 입력 — 컨텍스트는 자동 변경을 하지 않는다.
        Mock 등 정수 아닌 속성은 isinstance 가드로 걸러 best-effort 로 동작한다.
        """
        try:
            cond = await self.condition_repo.latest()
        except Exception:  # noqa: BLE001 — context is best-effort
            return None
        if cond is None:
            return None
        bits: list[str] = []
        fatigue = getattr(cond, "fatigue_level", None)
        soreness = getattr(cond, "soreness", None)
        note = getattr(cond, "notes", None)
        if isinstance(fatigue, int):
            bits.append(f"피로도 {fatigue}/10")
        if isinstance(soreness, int):
            bits.append(f"근육통 {soreness}/5")
        if isinstance(note, str) and note.strip():
            bits.append(f"메모 '{note.strip()[:20]}'")
        if not bits:
            return None
        return "최근 컨디션: " + ", ".join(bits)

    async def _safety_block(self) -> str | None:
        """활성 부상/제약 전량을 한 줄로. **절대 잘리지 않는다**(안전 직결)."""
        if self.memory_repo is None:
            return None
        try:
            constraints = await self.memory_repo.get_constraints()
        except Exception as e:  # noqa: BLE001 — never break the prompt
            # 안전 직결: 조용히 삼키면 부상/제약 누락을 눈치채지 못한다 (ADR-025 손실 0).
            logger.error("CoachContext: constraint fetch failed, safety info may drop: {}", e)
            return None
        if not constraints:
            return None
        items = "; ".join(
            f"{'부상' if getattr(c, 'kind', None) == 'injury' else '제약'}:{c.text}"
            for c in constraints
        )
        return f"⚠️필수 제약(전량): {items}"

    async def _plan_summary(self) -> str | None:
        """활성 주간 플랜의 목표·진척을 한 줄로(ADR-024). 목표가 없으면 None →
        프롬프트는 플랜을 언급하지 않고 코치는 단발 제안으로 진행한다(fallback)."""
        if self.plan_repo is None:
            return None
        try:
            plan = await self.plan_repo.get_active()
            if plan is None or getattr(plan, "id", None) is None:
                return None
            items = await self.plan_repo.progress(plan.id)
        except Exception as e:  # noqa: BLE001 — context is best-effort
            logger.warning("CoachContext: plan progress fetch failed: {}", e)
            return None
        return summarize_progress(items)

    async def _recent_memo(self) -> str | None:
        """2층 자유텍스트 최근 N건. 비거나 검색 실패해도 안전에는 영향 없음."""
        if self.memory_repo is None:
            return None
        try:
            facts = await self.memory_repo.recent_facts(limit=_MAX_RECENT_FACTS)
        except Exception:  # noqa: BLE001 — best-effort
            return None
        if not facts:
            return None
        return "메모: " + " / ".join(f.text for f in facts)

    async def _get_baselines(self) -> list:
        """1층 기준선 전량(없거나 조회 실패면 빈 리스트). 첫-세션 판정·재평가 힌트 공용."""
        if self.memory_repo is None:
            return []
        try:
            result = await self.memory_repo.get_baseline()
        except Exception:  # noqa: BLE001 — best-effort
            return []
        return result if isinstance(result, list) else []

    def _first_session_block(self, profile) -> str:
        """ADR-028 첫 체력검증 지시문 + 온보딩 자가보고 시드.

        고정값을 던지지 말고, 온보딩 시드를 대화로 확인·보정한 뒤 보수적(≈70%) 시작을
        제안하라고 코치에게 지시한다. 시드가 없으면 대화로 수집(안 행복한 경로)."""
        seed = _parse_assessment_seed(profile)
        if seed:
            seed_line = "온보딩 자가보고 시드: " + ", ".join(
                f"{ex} {val}{'초' if ex in _TIMER_EXERCISES else '회'}"
                for ex, val in seed.items()
            )
        else:
            seed_line = "온보딩 자가보고 없음(대화로 종목별 가능 횟수를 물어 수집)."
        # 짧게 유지 — 길고 메타적인 지시는 9b 의 구조화(JSON) 출력 안정성을 떨어뜨린다.
        return (
            f"🔰 첫 세션(기준선 없음): 대화로 체력 확인. {seed_line} 시드가 맞는지 확인한 뒤 "
            "70% 보수적 시작을 제안하고, 동의하면 set_baseline 으로 저장. 한계 측정 금지."
        )

    async def _calendar_signals(self) -> CalendarSignals:
        # Phase-8 wires app.core.calendar_metrics here. Until then return zeros
        # so the prompt simply omits weekly-pattern hints.
        if self.calendar_signals_fn is None:
            return CalendarSignals()
        try:
            result = await self.calendar_signals_fn()  # type: ignore[misc]
            if isinstance(result, CalendarSignals):
                return result
        except Exception:  # noqa: BLE001 — never break the prompt over a hook error
            pass
        return CalendarSignals()


def parse_available_times(profile) -> list[str]:
    """UserProfile.available_times is a JSON-encoded list; defensive parse."""
    raw = getattr(profile, "available_times", None)
    if not raw:
        return []
    try:
        return list(json.loads(raw))
    except (TypeError, ValueError):
        return []


def _parse_assessment_seed(profile) -> dict[str, int]:
    """UserProfile.assessment_json (온보딩 자가보고 원본 시드) defensive parse.

    값이 정수로 떨어지지 않으면 버린다(LLM/UI 오염 방지). 키는 종목명."""
    raw = getattr(profile, "assessment_json", None)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    seed: dict[str, int] = {}
    for ex, val in data.items():
        try:
            seed[str(ex)] = int(val)
        except (TypeError, ValueError):
            continue
    return seed


def _baseline_reassess_hint(baselines: list) -> str | None:
    """기준선이 ``_BASELINE_REASSESS_DAYS`` 이상 지났으면 재평가 권유 힌트(ADR-028).

    가장 오래된 ``updated_at`` 기준. tz 혼선을 피하려 항상 UTC now 로 비교한다."""
    stamps: list[datetime] = []
    for b in baselines:
        ts = getattr(b, "updated_at", None)
        if isinstance(ts, datetime):
            stamps.append(ts if ts.tzinfo else ts.replace(tzinfo=UTC))
    if not stamps:
        return None
    oldest = min(stamps)
    age_days = (datetime.now(UTC) - oldest).days
    if age_days < _BASELINE_REASSESS_DAYS:
        return None
    return (
        f"기준선이 {age_days}일 지났습니다 — 너무 쉽거나 어렵지 않은지 물어보고 필요하면 "
        "set_baseline 으로 재측정(갱신)을 제안하세요."
    )


async def compute_effective_sessions(
    session_repo: _SessionRepo,
    set_repo: _SetLogRepo,
    *,
    recent_sessions: int = 5,
) -> list:
    """SetLog 가 1개 이상 있는 최근 세션만(최대 ``recent_sessions`` 개).

    연결만 하고 운동 안 한 세션은 제외 — 빈 리스트면 신규/첫 사용자로 취급한다.
    build() 와 첫-세션 판정(is_first_session)이 공유하는 단일 진실."""
    raw_sessions = await session_repo.get_recent(limit=recent_sessions * 4)
    effective: list = []
    for s in raw_sessions:
        if s.id is None:
            continue
        try:
            sl = await set_repo.get_by_session(s.id)
        except Exception:  # noqa: BLE001 — best-effort
            sl = []
        if sl:
            effective.append(s)
            if len(effective) >= recent_sessions:
                break
    return effective


async def is_first_session(
    memory_repo: _MemoryRepo,
    session_repo: _SessionRepo,
    set_repo: _SetLogRepo,
    *,
    recent_sessions: int = 5,
) -> bool:
    """첫 세션 판정 (ADR-028): 효과 세션도 기준선도 없을 때 True.

    ws_voice 가 능동 인사 메시지를 첫-세션용으로 고를 때, 그리고 테스트가 검증할 때
    쓴다. 컨텍스트 빌더 build() 의 첫-세션 블록과 동일 기준."""
    eff = await compute_effective_sessions(
        session_repo, set_repo, recent_sessions=recent_sessions
    )
    if eff:
        return False
    try:
        baselines = await memory_repo.get_baseline()
    except Exception:  # noqa: BLE001 — best-effort
        baselines = []
    return not baselines
