"""MeloTTSService — Pipecat TTS wrapper for MeloTTSClient (ADR-006, ADR-012)."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from loguru import logger
from pipecat.frames.frames import Frame, TTSAudioRawFrame
from pipecat.services.settings import TTSSettings
from pipecat.services.tts_service import TTSService

from app.adapters.tts.melo_client import MeloTTSClient
from app.utils.latency import LatencyTracker

_CHANNELS = 1


class MeloTTSService(TTSService):
    """Pipecat adapter wrapping `MeloTTSClient` — native sample rate (44.1kHz Korean)."""

    def __init__(self, client: MeloTTSClient, **kwargs) -> None:
        # Pipecat 1.3+:
        #  * push_start_frame=True — base class creates the audio context and
        #    emits TTSStartedFrame before run_tts yields. Without this, our
        #    TTSAudioRawFrame outputs never reach the transport.
        #  * stop_frame_timeout_s=30.0 — Melo synthesises a full sentence per
        #    yield (~5s first chunk on GPU), but Pipecat's default 3s queue-get
        #    timeout would tear down the audio context before our first frame
        #    arrives. 30s gives ample headroom for slower sentences.
        super().__init__(
            sample_rate=client.sample_rate,
            settings=TTSSettings(model=None, voice=None, language=None),
            push_start_frame=True,
            stop_frame_timeout_s=30.0,
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
