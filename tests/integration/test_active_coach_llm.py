"""Real-Ollama tests for the active coach (ADR-013).

These hit a live Ollama instance — they validate prompt behaviour, not just the
plumbing. Marked ``ollama`` so they can be deselected on CI.
"""

from __future__ import annotations

import pytest

from app.config import load_config
from app.core.coach_response import CoachResponse
from app.pipecat_services.ollama_service import StructuredOllamaProcessor
from app.prompts.coaching import PROACTIVE_OPENER_USER_MESSAGE

pytestmark = pytest.mark.ollama


async def _generate(text: str) -> CoachResponse:
    proc = StructuredOllamaProcessor(load_config())
    return await proc._generate(text)


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
