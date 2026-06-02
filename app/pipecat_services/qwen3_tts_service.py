"""Qwen3TTSService — Pipecat TTS wrapper for Qwen3TTSClient (ADR-006, ADR-012).

Sentence-batch streaming: yields one TTSAudioRawFrame per sentence as soon
as the upstream client finishes synthesising it.  First-chunk latency is
measured via LatencyTracker (`latency.tts.first_chunk`, ADR-018).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from loguru import logger
from pipecat.frames.frames import Frame, TTSAudioRawFrame
from pipecat.services.tts_service import TTSService

from app.adapters.tts.qwen3_client import Qwen3TTSClient
from app.utils.latency import LatencyTracker

_CHANNELS = 1


class Qwen3TTSService(TTSService):
    """Pipecat adapter wrapping `Qwen3TTSClient` — 24kHz mono PCM frames."""

    def __init__(self, client: Qwen3TTSClient, **kwargs) -> None:
        # model/voice/language pinned to None — we don't expose them as runtime
        # settings (single voice via cached ref WAV).  Pipecat's TTSSettings
        # validator requires every field to be initialised (not NOT_GIVEN).
        super().__init__(
            sample_rate=client.sample_rate,
            model=None,
            voice=None,
            language=None,
            **kwargs,
        )
        self._client = client

    async def run_tts(
        self, text: str, context_id: str
    ) -> AsyncGenerator[Frame | None, None]:
        if not text or not text.strip():
            return
        tracker = LatencyTracker("tts.first_chunk")
        tracker.__enter__()
        first = True
        async for pcm in self._client.stream(text):
            if first:
                tracker.stop()
                first = False
            yield TTSAudioRawFrame(
                audio=pcm,
                sample_rate=self._client.sample_rate,
                num_channels=_CHANNELS,
                context_id=context_id,
            )
        if first:
            # Upstream produced no chunks (empty paragraph after strip) — still emit.
            tracker.stop()
            logger.debug("Qwen3TTSService: no chunks produced for text={!r}", text)
