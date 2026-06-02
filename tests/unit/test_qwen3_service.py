"""Qwen3TTSService unit tests — mock client, no GPU."""

from collections.abc import AsyncIterator

import pytest
from pipecat.frames.frames import (
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    TextFrame,
    TTSAudioRawFrame,
)
from pipecat.tests.utils import run_test

from app.pipecat_services.qwen3_tts_service import Qwen3TTSService


class _FakeQwen3Client:
    """Stub Qwen3TTSClient that yields three fake PCM chunks."""

    sample_rate = 24000

    async def stream(self, text) -> AsyncIterator[bytes]:
        for i in range(3):
            yield bytes([i]) * 240   # 240 byte PCM blob per "sentence"


@pytest.mark.asyncio
async def test_text_frame_to_three_audio_frames():
    """LLM response envelope around a TextFrame → 3 PCM frames from the fake client."""
    service = Qwen3TTSService(_FakeQwen3Client())
    down, _ = await run_test(
        service,
        frames_to_send=[
            LLMFullResponseStartFrame(),
            TextFrame(text="문장 하나입니다. 문장 둘입니다. 문장 셋입니다."),
            LLMFullResponseEndFrame(),
        ],
    )
    # 3 sentences × 3 fake PCM chunks per sentence = 9 TTSAudioRawFrames.
    audio_frames = [f for f in down if isinstance(f, TTSAudioRawFrame)]
    assert len(audio_frames) == 9
    for f in audio_frames:
        assert f.sample_rate == 24000
        assert f.num_channels == 1
        assert len(f.audio) == 240
