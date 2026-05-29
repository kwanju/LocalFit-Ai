import asyncio
import logging
from dataclasses import dataclass

import numpy as np
import torch
from silero_vad import VADIterator, get_speech_timestamps, load_silero_vad

from app.config import AppConfig

logger = logging.getLogger(__name__)

_SILERO_SAMPLE_RATE = 16000
# silero-vad streaming requires fixed 512-sample windows at 16kHz (~32ms).
_VAD_WINDOW = 512
# Pad kept before/after a detected utterance so STT doesn't clip onsets.
_SPEECH_PAD_MS = 200


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

    def new_stream(self) -> "VADStreamSession":
        """Open a stateful streaming segmenter sharing this loaded model (S2S live)."""
        return VADStreamSession(self._model, self._threshold, self._min_silence_ms)


class VADStreamSession:
    """Stateful streaming VAD: feed 16kHz mono PCM as it arrives, get back each
    completed utterance (speech bounded by min_silence). Wraps silero VADIterator,
    which emits 'start'/'end' events on fixed 512-sample windows.
    """

    def __init__(self, model: object, threshold: float, min_silence_ms: int) -> None:
        self._iter = VADIterator(
            model,
            threshold=threshold,
            sampling_rate=_SILERO_SAMPLE_RATE,
            min_silence_duration_ms=min_silence_ms,
        )
        self._tail = np.empty(0, dtype=np.float32)  # leftover < one window
        self._lookback = np.empty(0, dtype=np.float32)  # pre-speech pad while idle
        self._utterance: list[np.ndarray] | None = None  # windows collected while in speech
        self._pad = int(_SPEECH_PAD_MS * _SILERO_SAMPLE_RATE / 1000)

    def feed(self, pcm: np.ndarray) -> list[np.ndarray]:
        """Feed mono float32 @16kHz; return any utterances completed in this chunk."""
        completed: list[np.ndarray] = []
        data = np.concatenate([self._tail, pcm])
        n_windows = len(data) // _VAD_WINDOW
        for i in range(n_windows):
            window = np.ascontiguousarray(data[i * _VAD_WINDOW : (i + 1) * _VAD_WINDOW])
            event = self._iter(torch.from_numpy(window), return_seconds=False)
            starting = event is not None and "start" in event
            ending = event is not None and "end" in event

            if starting and self._utterance is None:
                self._utterance = [self._lookback.copy(), window]
            elif self._utterance is not None:
                self._utterance.append(window)
            else:
                self._lookback = np.concatenate([self._lookback, window])[-self._pad :]

            if ending and self._utterance is not None:
                completed.append(np.concatenate(self._utterance))
                self._utterance = None
                self._lookback = np.empty(0, dtype=np.float32)
        self._tail = data[n_windows * _VAD_WINDOW :]
        return completed

    def reset(self) -> None:
        self._iter.reset_states()
        self._tail = np.empty(0, dtype=np.float32)
        self._lookback = np.empty(0, dtype=np.float32)
        self._utterance = None
