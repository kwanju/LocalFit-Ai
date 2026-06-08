"""Qwen3TTSService — Pipecat TTS wrapper for Qwen3TTSClient (ADR-006, ADR-012).

Sentence-batch streaming: yields one TTSAudioRawFrame per sentence as soon
as the upstream client finishes synthesising it.  First-chunk latency is
measured via LatencyTracker (`latency.tts.first_chunk`, ADR-018).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from loguru import logger
from pipecat.frames.frames import Frame, TTSAudioRawFrame
from pipecat.services.settings import TTSSettings
from pipecat.services.tts_service import TTSService

from app.adapters.tts.qwen3_client import Qwen3TTSClient
from app.utils.latency import LatencyTracker

_CHANNELS = 1


class Qwen3TTSService(TTSService):
    """Pipecat adapter wrapping `Qwen3TTSClient` — 24kHz mono PCM frames."""

    def __init__(self, client: Qwen3TTSClient, **kwargs) -> None:
        # Pipecat 1.3+:
        #  * settings=TTSSettings(...) — model/voice/language live there now,
        #    not as direct kwargs. All None (single cached voice).
        #  * push_start_frame=True — base class creates the audio context and
        #    emits TTSStartedFrame before run_tts yields. Required since 1.3
        #    or TTSAudioRawFrame outputs never reach the transport.
        #  * stop_frame_timeout_s=30.0 — faster-qwen3-tts first-chunk latency is
        #    ~1s on RTX 5090 (sentence-batch), but Pipecat's default 3s queue-get
        #    timeout is still cut close for long first sentences; keep generous
        #    margin so the audio context isn't torn down before the first frame.
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
            # Upstream produced no chunks (empty paragraph after strip) — still emit.
            tracker.stop()
            logger.debug("Qwen3TTSService: no chunks produced for text={!r}", text)
