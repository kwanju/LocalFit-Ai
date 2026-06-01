"""MockTTSService — Phase 2 mock TTS for pipeline shell testing.

Subclasses TTSService. Returns a 100ms silent PCM frame regardless of text.
Real TTS (Qwen3-TTS + SDPA) is wired in Phase 3.
"""

from collections.abc import AsyncGenerator

from loguru import logger
from pipecat.frames.frames import Frame, TTSAudioRawFrame
from pipecat.services.tts_service import TTSService

_SAMPLE_RATE = 16000
_CHANNELS = 1
# 100ms of silence: 16000 samples/s * 0.1s * 2 bytes/sample
_SILENCE_BYTES = bytes(_SAMPLE_RATE // 10 * _CHANNELS * 2)


class MockTTSService(TTSService):
    """Silent-PCM mock. Ignores text; yields one 100ms silent TTSAudioRawFrame."""

    def __init__(self, **kwargs) -> None:
        super().__init__(sample_rate=_SAMPLE_RATE, **kwargs)

    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame | None, None]:
        logger.debug("MockTTSService: synthesising '{}' → 100ms silence", text)
        yield TTSAudioRawFrame(
            audio=_SILENCE_BYTES,
            sample_rate=_SAMPLE_RATE,
            num_channels=_CHANNELS,
            context_id=context_id,
        )
