"""MeloTTSService — Pipecat TTS wrapper for MeloTTSClient (ADR-006, ADR-012)."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from loguru import logger
from pipecat.frames.frames import Frame, TTSAudioRawFrame
from pipecat.services.tts_service import TTSService

from app.adapters.tts.melo_client import MeloTTSClient
from app.utils.latency import LatencyTracker

_CHANNELS = 1


class MeloTTSService(TTSService):
    """Pipecat adapter wrapping `MeloTTSClient` — native sample rate (44.1kHz Korean)."""

    def __init__(self, client: MeloTTSClient, **kwargs) -> None:
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
            tracker.stop()
            logger.debug("MeloTTSService: no chunks produced for text={!r}", text)
