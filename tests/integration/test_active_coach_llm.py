"""Real-Ollama tests for the active coach (ADR-013).

These hit a live Ollama instance — they validate prompt behaviour, not just the
plumbing. Marked ``ollama`` so they can be deselected on CI.
"""

from __future__ import annotations

import pytest

from app.config import load_config
from app.core.coach_response import CoachResponse
from app.pipecat_services.ollama_service import StructuredOllamaProcessor
from app.prompts.coaching import (
    FIRST_SESSION_OPENER_USER_MESSAGE,
    PROACTIVE_OPENER_USER_MESSAGE,
)

pytestmark = pytest.mark.ollama

# ADR-028 첫 세션 컨텍스트 — 실제 ws_voice 가 주입하는 "🔰 첫 세션" 블록을 모사한다.
_FIRST_SESSION_CONTEXT = (
    "사용자: 30대 / 🔰 첫 세션(기준선 미설정): 고정값을 던지지 말고 대화로 체력을 "
    "확인하세요. 온보딩 자가보고 시드: 푸시업 15회, 플랭크 30초 시드 값을 사용자에게 "
    "확인·보정한 뒤 약 70% 수준의 보수적 시작을 제안하고, 사용자가 동의하면 set_baseline "
    "으로 종목별 기준선을 저장하세요. 한계(최대 1세트) 측정은 시키지 마세요."
)


class _FixedContext:
    def __init__(self, text: str) -> None:
        self._text = text

    async def build(self, *, recent_sessions: int = 5, now=None) -> str:
        return self._text


async def _generate(text: str) -> CoachResponse:
    proc = StructuredOllamaProcessor(load_config())
    return await proc._generate(text)


async def _generate_with_context(context: str, text: str) -> CoachResponse:
    proc = StructuredOllamaProcessor(load_config(), _FixedContext(context))
    return await proc._generate(text)


@pytest.mark.asyncio
async def test_proactive_opener_returns_valid_response_with_plan() -> None:
    """능동 인사가 valid CoachResponse + propose_set 을 낸다 (thinking-off 회귀 가드).

    qwen3.5:9b thinking 이 켜지면 reasoning 이 num_ctx 를 채워 JSON 이 빈 문자열로 잘려
    ``_generate`` 가 예외를 던진다(2026-06-12 능동 인사 전면 실패 버그). 이 테스트가
    실제 Ollama 로 그 회귀를 잡는다 — 예외 없이 text + propose_set 이 나와야 한다."""
    response = await _generate(PROACTIVE_OPENER_USER_MESSAGE)
    assert response.text, "능동 인사 text 가 비었습니다 (thinking 폭주 의심)"
    proposes = [a for a in response.actions if a.type == "propose_set"]
    assert len(proposes) >= 1, f"능동 인사에 운동 제안(propose_set)이 없습니다: {response}"


@pytest.mark.asyncio
async def test_proactive_opener_under_120_chars_soft_cap() -> None:
    """능동 인사 응답 길이 ≤ 120자 (목표 70자, 안전망 120자) — ADR-013 §응답 길이."""
    response = await _generate(PROACTIVE_OPENER_USER_MESSAGE)
    assert response.text
    assert len(response.text) <= 120, (
        f"능동 인사가 120자(소프트 안전망)를 넘었습니다 (len={len(response.text)}): "
        f"{response.text!r}. 70자 목표 — 시스템 프롬프트 추가 튜닝 필요."
    )


@pytest.mark.asyncio
async def test_condition_report_logs_and_does_not_auto_start() -> None:
    """ADR-023: 컨디션 발화 → log_condition 기록, start_counting 직접 발행 금지.

    "피곤·뻐근" 발화에 코치가 컨디션을 기록(log_condition)하고, 자동으로 카운팅을
    시작하지 않아야 한다(강도 조절은 propose_set→확답 게이트). phase v4-3 핵심 흐름."""
    response = await _generate("오늘 너무 피곤하고 어깨가 뻐근해요")
    logs = [a for a in response.actions if a.type == "log_condition"]
    starts = [a for a in response.actions if a.type == "start_counting"]
    assert len(logs) >= 1, f"컨디션 발화에 log_condition 이 없습니다: {response}"
    assert starts == [], f"컨디션만 말했는데 start_counting 자동 발행됨: {response}"


@pytest.mark.asyncio
async def test_proactive_principle_accepts_user_redirect() -> None:
    """수용 정책: 사용자가 '오늘은 내가 정할게' 발화 시 LLM이 능동 제안 자제."""
    proc = StructuredOllamaProcessor(load_config())
    response = await proc._generate("오늘은 내가 정할게. 추천 안 해도 돼.")
    propose_actions = [a for a in response.actions if a.type == "propose_set"]
    start_actions = [a for a in response.actions if a.type == "start_counting"]
    assert propose_actions == [], (
        f"사용자가 제안 거부 의향 표현했는데 propose_set 발행됨: {response}"
    )
    assert start_actions == [], (
        f"사용자가 제안 거부 의향 표현했는데 start_counting 발행됨: {response}"
    )


@pytest.mark.asyncio
async def test_explicit_plan_emits_propose_set_not_start() -> None:
    """명시적 운동 발화도 propose_set 으로 제안만 — start_counting 직접 발행 X (2026-06-09).

    실제 시작은 사용자 확답(ConfirmRule) 이 처리한다. LLM 의 start_counting 은 백엔드가
    무시(제안 전환)하므로 LLM 이 내면 안 된다.
    """
    response = await _generate("푸시업 10개 시작하자")
    propose = [a for a in response.actions if a.type == "propose_set"]
    start = [a for a in response.actions if a.type == "start_counting"]
    assert len(propose) >= 1, f"propose_set 기대: {response}"
    assert start == [], f"start_counting 직접 발행하면 안 됨: {response}"
    assert propose[0].exercise == "푸시업"


@pytest.mark.asyncio
async def test_first_session_does_not_auto_start_counting() -> None:
    """ADR-028 첫 세션: 능동 인사가 곧바로 운동을 시작(start_counting)시키지 않는다.

    "🔰 첫 세션" 컨텍스트에서는 대화로 체력을 확인하는 흐름이어야 하므로, 어떤 경우에도
    start_counting 을 직접 발행하면 안 된다(실제 시작은 propose_set→확답 게이트)."""
    response = await _generate_with_context(
        _FIRST_SESSION_CONTEXT, FIRST_SESSION_OPENER_USER_MESSAGE
    )
    assert response.text, "첫 세션 인사 text 가 비었습니다"
    starts = [a for a in response.actions if a.type == "start_counting"]
    assert starts == [], f"첫 세션인데 start_counting 자동 발행됨: {response}"
