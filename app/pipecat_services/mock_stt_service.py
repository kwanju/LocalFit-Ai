"""MockSTTService — Phase 2 mock STT for pipeline shell testing.

Subclasses SegmentedSTTService (VAD-triggered segmented STT).
Returns a fixed transcription "테스트" regardless of audio content.
Real STT is wired in Phase 4 (faster-whisper).
"""

from collections.abc import AsyncGenerator

from loguru import logger
from pipecat.frames.frames import Frame, TranscriptionFrame
from pipecat.services.stt_service import SegmentedSTTService
from pipecat.utils.time import time_now_iso8601


class MockSTTService(SegmentedSTTService):
    """Fixed-transcription mock. Ignores audio bytes; always yields '테스트'."""

    def __init__(self, **kwargs) -> None:
        # model=None / language=None satisfy STTSettings.validate_complete() without warning.
        super().__init__(sample_rate=16000, model=None, language=None, **kwargs)

    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame | None, None]:
        logger.debug("MockSTTService: transcribing {} bytes → '테스트'", len(audio))
        yield TranscriptionFrame(
            text="테스트",
            user_id="user",
            timestamp=time_now_iso8601(),
        )
