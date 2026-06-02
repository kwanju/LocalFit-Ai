"""MeloTTSService unit tests — mock client, no GPU."""

from collections.abc import AsyncIterator

import pytest
from pipecat.frames.frames import (
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    TextFrame,
    TTSAudioRawFrame,
)
from pipecat.tests.utils import run_test

from app.pipecat_services.melo_tts_service import MeloTTSService


class _FakeMeloClient:
    sample_rate = 44100

    async def stream(self, text) -> AsyncIterator[bytes]:
        for i in range(2):
            yield bytes([i]) * 441  # arbitrary fake PCM


@pytest.mark.asyncio
async def test_text_frame_to_two_audio_frames():
    service = MeloTTSService(_FakeMeloClient())
    down, _ = await run_test(
        service,
        frames_to_send=[
            LLMFullResponseStartFrame(),
            TextFrame(text="짧은 문장. 또 다른 문장."),
            LLMFullResponseEndFrame(),
        ],
    )
    # 2 sentences × 2 fake PCM chunks per sentence = 4 TTSAudioRawFrames.
    audio_frames = [f for f in down if isinstance(f, TTSAudioRawFrame)]
    assert len(audio_frames) == 4
    for f in audio_frames:
        assert f.sample_rate == 44100
        assert f.num_channels == 1
        assert len(f.audio) == 441
