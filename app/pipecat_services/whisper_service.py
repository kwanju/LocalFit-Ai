"""LocalFitWhisperSTTService — Pipecat STT wrapper over FasterWhisperClient.

Option B (ADR-005, phase-4 §4-2): subclass `SegmentedSTTService` so VAD events
drive transcription, while the 16kHz resample guarantee stays in the domain
adapter (FasterWhisperClient). Pipecat's official WhisperSTTService is bypassed
to keep sample-rate enforcement explicit and the client mockable in tests.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from loguru import logger
from pipecat.frames.frames import Frame, TranscriptionFrame
from pipecat.services.stt_service import SegmentedSTTService
from pipecat.utils.time import time_now_iso8601

from app.adapters.stt.faster_whisper_client import FasterWhisperClient
from app.utils.latency import LatencyTracker

_TARGET_SR = 16000  # ADR-005: faster-whisper는 16kHz 가정


class LocalFitWhisperSTTService(SegmentedSTTService):
    """Pipecat segmented STT adapter wrapping `FasterWhisperClient`.

    Pipecat's SegmentedSTTService buffers audio between
    VADUserStartedSpeakingFrame / VADUserStoppedSpeakingFrame, then hands a
    finalized WAV blob to `run_stt`. We forward the blob to the domain client
    (which enforces 16kHz resample and timeout) and emit one TranscriptionFrame.
    """

    def __init__(self, client: FasterWhisperClient, **kwargs) -> None:
        # Pipecat's STTSettings validator requires model/language to be set
        # (NOT_GIVEN trips a warning). Pass None to skip the warning path.
        super().__init__(sample_rate=_TARGET_SR, model=None, language=None, **kwargs)
        self._client = client

    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame | None, None]:
        if not audio:
            logger.warning("LocalFitWhisperSTTService: empty audio segment, skipping")
            return
        try:
            with LatencyTracker("stt.transcribe"):
                result = await self._client.transcribe(audio, sample_rate=self.sample_rate)
        except Exception as e:
            logger.error("LocalFitWhisperSTTService: transcription error: {}", e)
            return
        text = result.text.strip()
        if not text:
            logger.debug("LocalFitWhisperSTTService: blank transcript, skipping frame")
            return
        yield TranscriptionFrame(
            text=text,
            user_id="user",
            timestamp=time_now_iso8601(),
        )
