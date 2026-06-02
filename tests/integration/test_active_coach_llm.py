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
async def test_explicit_start_emits_start_counting() -> None:
    """사용자가 명시적으로 '푸시업 10개 시작' → start_counting 액션 발행."""
    response = await _generate("푸시업 10개 시작하자")
    start_actions = [a for a in response.actions if a.type == "start_counting"]
    assert len(start_actions) >= 1, (
        f"명시적 시작 발화에 start_counting 액션이 없습니다: {response}"
    )
    assert start_actions[0].exercise == "푸시업"
    assert start_actions[0].reps == 10
