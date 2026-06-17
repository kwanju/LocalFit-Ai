"""SafetyGuardProcessor — intercepts injury/emergency keywords (ADR-013)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from pipecat.frames.frames import Frame, TextFrame, TranscriptionFrame
from pipecat.tests.utils import run_test
from pipecat.utils.time import time_now_iso8601

from app.messages import MSG_CONSTRAINT_REMEMBERED
from app.pipecat_services.frames import SafetyResponseFrame
from app.pipecat_services.processors.safety_guard import SafetyGuardProcessor


async def _send(text: str) -> list[Frame]:
    down, _ = await run_test(
        SafetyGuardProcessor(),
        frames_to_send=[
            TranscriptionFrame(text=text, user_id="u", timestamp=time_now_iso8601())
        ],
    )
    return list(down)


@pytest.mark.parametrize(
    "text",
    [
        "허리가 아파요",
        "발목을 삐었어요",
        "숨이 안 쉬어져요",
        "어깨가 욱신거려요",
        "가슴이 조여와요",
    ],
)
async def test_unsafe_intercepts_llm(text: str) -> None:
    frames = await _send(text)
    safety = [f for f in frames if isinstance(f, SafetyResponseFrame)]
    transcripts = [f for f in frames if isinstance(f, TranscriptionFrame)]
    kinds = [type(f).__name__ for f in frames]
    assert len(safety) == 1, f"expected SafetyResponseFrame for '{text}', got {kinds}"
    # original TranscriptionFrame must NOT propagate downstream (LLM bypassed)
    assert transcripts == []


async def test_safe_passthrough() -> None:
    frames = await _send("오늘 컨디션 좋아요")
    transcripts = [f for f in frames if isinstance(f, TranscriptionFrame)]
    safety = [f for f in frames if isinstance(f, SafetyResponseFrame)]
    assert len(transcripts) == 1
    assert safety == []


async def test_empty_text_passthrough() -> None:
    down, _ = await run_test(
        SafetyGuardProcessor(),
        frames_to_send=[TranscriptionFrame(text="", user_id="u", timestamp="x")],
    )
    assert any(isinstance(f, TranscriptionFrame) for f in down)


async def _send_with_recorder(text: str, cb: AsyncMock) -> list[Frame]:
    down, _ = await run_test(
        SafetyGuardProcessor(record_constraint=cb),
        frames_to_send=[
            TranscriptionFrame(text=text, user_id="u", timestamp=time_now_iso8601())
        ],
    )
    return list(down)


async def test_body_pain_promoted_to_constraint() -> None:
    """ADR-025 — 부위 통증(MODERATE)은 1층 제약으로 즉시 저장 + 응답에 통지."""
    cb = AsyncMock()
    frames = await _send_with_recorder("왼쪽 어깨가 아파요", cb)
    cb.assert_awaited_once()
    action = cb.call_args.args[0]
    assert action.kind == "injury"
    assert action.text == "왼쪽 어깨가 아파요"
    safety = [f for f in frames if isinstance(f, SafetyResponseFrame)]
    assert len(safety) == 1
    assert MSG_CONSTRAINT_REMEMBERED in safety[0].text


async def test_emergency_not_promoted() -> None:
    """급성 응급(EMERGENCY)은 영구 제약이 아니므로 저장하지 않는다."""
    cb = AsyncMock()
    frames = await _send_with_recorder("숨이 안 쉬어져요", cb)
    cb.assert_not_awaited()
    safety = [f for f in frames if isinstance(f, SafetyResponseFrame)]
    assert len(safety) == 1
    assert MSG_CONSTRAINT_REMEMBERED not in safety[0].text


async def test_transient_fatigue_not_promoted() -> None:
    """피로는 부상이 아니라 컨디션 — SafetyGuard 가 가로채지도, 제약으로 승격하지도 않는다
    (코치 LLM 이 log_condition 처리, ADR-023/033)."""
    cb = AsyncMock()
    await _send_with_recorder("너무 피곤해요", cb)
    cb.assert_not_awaited()


async def test_non_user_text_passthrough() -> None:
    """LLM-generated TextFrames (not InputTextRawFrame) must not be safety-checked."""
    down, _ = await run_test(
        SafetyGuardProcessor(),
        frames_to_send=[TextFrame(text="허리가 아파요")],
    )
    text_frames = [f for f in down if type(f) is TextFrame]
    assert len(text_frames) == 1
    assert text_frames[0].text == "허리가 아파요"
    assert not any(isinstance(f, SafetyResponseFrame) for f in down)
