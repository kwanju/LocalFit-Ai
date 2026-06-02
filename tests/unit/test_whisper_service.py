"""Phase 4 §4-2 — LocalFitWhisperSTTService frame contract.

Mock-client injection (Option B 채택 이유): VAD bracketed audio → TranscriptionFrame.
"""

from __future__ import annotations

import pytest
from pipecat.frames.frames import (
    AudioRawFrame,
    TranscriptionFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.tests.utils import run_test

from app.adapters.stt.faster_whisper_client import STTResult
from app.pipecat_services.whisper_service import LocalFitWhisperSTTService

_SILENCE_100MS = bytes(16000 // 10 * 2)  # 100ms @ 16kHz int16 mono


class _FakeWhisperClient:
    """Stand-in for FasterWhisperClient; records the last audio it received."""

    def __init__(self, text: str = "안녕하세요") -> None:
        self._text = text
        self.last_audio: bytes | None = None
        self.last_sample_rate: int | None = None

    async def transcribe(self, audio_bytes: bytes, sample_rate: int | None = None) -> STTResult:
        self.last_audio = audio_bytes
        self.last_sample_rate = sample_rate
        return STTResult(text=self._text, language="ko", duration_ms=12)


@pytest.mark.asyncio
async def test_vad_bracketed_audio_yields_transcription_frame() -> None:
    """VAD start + audio + VAD stop → exactly one finalized TranscriptionFrame."""
    client = _FakeWhisperClient(text="스쿼트 시작할게요")
    service = LocalFitWhisperSTTService(client)
    audio_frame = AudioRawFrame(audio=_SILENCE_100MS, sample_rate=16000, num_channels=1)

    down, _ = await run_test(
        service,
        frames_to_send=[
            VADUserStartedSpeakingFrame(),
            audio_frame,
            VADUserStoppedSpeakingFrame(),
        ],
    )

    transcriptions = [f for f in down if isinstance(f, TranscriptionFrame)]
    frame_names = [type(f).__name__ for f in down]
    assert len(transcriptions) == 1, f"expected 1 TranscriptionFrame, got {frame_names}"
    tf = transcriptions[0]
    assert tf.text == "스쿼트 시작할게요"
    assert tf.user_id == "user"
    assert tf.finalized is True
    # Pipecat ships the buffered audio as a WAV — the RIFF header should survive.
    assert client.last_audio is not None and client.last_audio[:4] == b"RIFF"
    # SegmentedSTTService passes its current sample rate as the segment sample_rate.
    assert client.last_sample_rate == 16000


@pytest.mark.asyncio
async def test_empty_transcript_is_skipped() -> None:
    """Blank STT output (silence) must not push an empty TranscriptionFrame."""
    client = _FakeWhisperClient(text="   ")
    service = LocalFitWhisperSTTService(client)
    audio_frame = AudioRawFrame(audio=_SILENCE_100MS, sample_rate=16000, num_channels=1)

    down, _ = await run_test(
        service,
        frames_to_send=[
            VADUserStartedSpeakingFrame(),
            audio_frame,
            VADUserStoppedSpeakingFrame(),
        ],
    )
    assert not [f for f in down if isinstance(f, TranscriptionFrame)]
