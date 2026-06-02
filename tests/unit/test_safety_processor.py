"""SafetyGuardProcessor — intercepts injury/emergency keywords (ADR-013)."""

from __future__ import annotations

import pytest
from pipecat.frames.frames import Frame, TextFrame, TranscriptionFrame
from pipecat.tests.utils import run_test
from pipecat.utils.time import time_now_iso8601

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
