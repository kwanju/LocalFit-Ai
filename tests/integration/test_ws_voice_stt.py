"""Phase 4 §4-8 — S2C 라운드트립: audio (+VAD) → TranscriptionFrame → TextFrame.

LocalFitWhisperSTTService + MockLLMProcessor 만 결합한 in-process 파이프라인을
`pipecat.tests.utils.run_test` 로 흘려, 발화 시뮬레이션(VAD start/audio/VAD stop)이
실제 TranscriptionFrame을 만들고 LLM 단까지 도달하는지 검증한다.

GPU 없이 통과해야 하므로 STT 어댑터는 가짜 클라이언트로 주입한다.
"""

from __future__ import annotations

import pytest
from pipecat.frames.frames import (
    AudioRawFrame,
    TextFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.tests.utils import run_test

from app.adapters.stt.faster_whisper_client import STTResult
from app.pipecat_services.mock_llm_service import MockLLMProcessor
from app.pipecat_services.whisper_service import LocalFitWhisperSTTService

_SILENCE_100MS = bytes(16000 // 10 * 2)  # 100ms @ 16kHz int16 mono


class _FakeWhisperClient:
    def __init__(self, text: str) -> None:
        self._text = text

    async def transcribe(self, audio_bytes: bytes, sample_rate: int | None = None) -> STTResult:
        return STTResult(text=self._text, language="ko", duration_ms=15)


@pytest.mark.asyncio
async def test_s2c_roundtrip_audio_to_llm_echo() -> None:
    """S2C: audio + VAD → 'echo: 안녕하세요' TextFrame."""
    stt = LocalFitWhisperSTTService(_FakeWhisperClient(text="안녕하세요"))
    llm = MockLLMProcessor()
    pipeline = Pipeline([stt, llm])

    audio_frame = AudioRawFrame(audio=_SILENCE_100MS, sample_rate=16000, num_channels=1)
    down, _ = await run_test(
        pipeline,
        frames_to_send=[
            VADUserStartedSpeakingFrame(),
            audio_frame,
            VADUserStoppedSpeakingFrame(),
        ],
    )

    # MockLLMProcessor consumes the TranscriptionFrame and emits an echo TextFrame,
    # so only the TextFrame (and pass-through system frames) survive downstream.
    texts = [f for f in down if isinstance(f, TextFrame)]
    frame_names = [type(f).__name__ for f in down]
    echoed = [t for t in texts if t.text == "echo: 안녕하세요"]
    text_values = [t.text for t in texts]
    assert echoed, f"expected MockLLM echo TextFrame, got texts={text_values} frames={frame_names}"
