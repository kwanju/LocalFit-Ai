import asyncio
import logging
from dataclasses import dataclass

import numpy as np
import torch
from silero_vad import get_speech_timestamps, load_silero_vad

from app.config import AppConfig

logger = logging.getLogger(__name__)

_SILERO_SAMPLE_RATE = 16000


@dataclass
class VADSegment:
    start_ms: int
    end_ms: int


class SileroVADWrapper:
    def __init__(self, config: AppConfig) -> None:
        self._threshold: float = config.vad.threshold
        self._min_silence_ms: int = config.vad.min_silence_ms
        logger.info(
            "Loading silero-vad threshold=%.2f min_silence_ms=%d",
            self._threshold,
            self._min_silence_ms,
        )
        self._model = load_silero_vad()
        logger.info("silero-vad loaded")

    def _detect_sync(self, audio: np.ndarray, sample_rate: int) -> list[VADSegment]:
        tensor = torch.FloatTensor(audio)
        timestamps = get_speech_timestamps(
            tensor,
            self._model,
            threshold=self._threshold,
            min_silence_duration_ms=self._min_silence_ms,
            sampling_rate=sample_rate,
        )
        return [
            VADSegment(
                start_ms=ts["start"] * 1000 // sample_rate,
                end_ms=ts["end"] * 1000 // sample_rate,
            )
            for ts in timestamps
        ]

    async def detect(
        self, audio: np.ndarray, sample_rate: int = _SILERO_SAMPLE_RATE
    ) -> list[VADSegment]:
        """Detect speech segments; returns list of start/end in milliseconds."""
        try:
            return await asyncio.to_thread(self._detect_sync, audio, sample_rate)
        except Exception as e:
            logger.error("VAD detection failed: %s", e)
            raise

    def has_speech(self, audio: np.ndarray, sample_rate: int = _SILERO_SAMPLE_RATE) -> bool:
        """Synchronous quick check — True if any speech segment is detected."""
        try:
            tensor = torch.FloatTensor(audio)
            timestamps = get_speech_timestamps(
                tensor,
                self._model,
                threshold=self._threshold,
                sampling_rate=sample_rate,
            )
            return len(timestamps) > 0
        except Exception as e:
            logger.error("VAD has_speech check failed: %s", e)
            return False
