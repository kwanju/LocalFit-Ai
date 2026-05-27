import asyncio
import io
import logging
import sys
import time
import wave

import numpy as np
from faster_whisper import WhisperModel

from app.adapters.stt.protocol import STTResult
from app.config import AppConfig

logger = logging.getLogger(__name__)


def _decode_audio(audio_bytes: bytes) -> np.ndarray:
    """Decode WAV bytes or raw int16 PCM bytes to float32 mono array."""
    if audio_bytes[:4] == b"RIFF":
        with wave.open(io.BytesIO(audio_bytes)) as wf:
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            raw = wf.readframes(wf.getnframes())
        if sampwidth != 2:
            raise ValueError(f"Unsupported PCM sample width: {sampwidth} bytes (expected 2)")
        pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        if n_channels > 1:
            pcm = pcm.reshape(-1, n_channels).mean(axis=1)
        return pcm
    # Raw int16 PCM (no header)
    return np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0


class FasterWhisperAdapter:
    def __init__(self, config: AppConfig) -> None:
        self._lang: str = config.stt.language
        cfg = config.stt
        logger.info(
            "Loading faster-whisper model=%s device=%s compute_type=%s",
            cfg.model,
            cfg.device,
            cfg.compute_type,
        )
        self._model = WhisperModel(cfg.model, device=cfg.device, compute_type=cfg.compute_type)
        logger.info("faster-whisper model loaded: %s", cfg.model)

    def _transcribe_sync(self, audio: np.ndarray) -> STTResult:
        t0 = time.monotonic()
        segments_gen, info = self._model.transcribe(audio, language=self._lang)
        parts = [seg.text.strip() for seg in segments_gen]
        text = " ".join(p for p in parts if p).strip()
        duration_ms = int((time.monotonic() - t0) * 1000)
        return STTResult(text=text, language=info.language, duration_ms=duration_ms)

    async def transcribe(self, audio_bytes: bytes, sample_rate: int = 16000) -> STTResult:
        try:
            audio = _decode_audio(audio_bytes)
            result = await asyncio.to_thread(self._transcribe_sync, audio)
            logger.info("Transcribed in %dms: %r", result.duration_ms, result.text[:80])
            return result
        except Exception as e:
            logger.error("STT transcription failed: %s", e)
            raise

    async def health(self) -> bool:
        return self._model is not None


async def _smoke_test(audio_path: str) -> None:
    from app.config import load_config

    config = load_config()
    adapter = FasterWhisperAdapter(config)

    if not await adapter.health():
        print("FasterWhisper 모델이 로드되지 않았습니다.", file=sys.stderr)
        sys.exit(1)

    with open(audio_path, "rb") as f:
        audio_bytes = f.read()

    result = await adapter.transcribe(audio_bytes)
    print(f"텍스트: {result.text}")
    print(f"언어: {result.language}")
    print(f"처리 시간: {result.duration_ms}ms")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python -m app.adapters.stt.whisper <audio.wav>", file=sys.stderr)
        sys.exit(1)
    asyncio.run(_smoke_test(sys.argv[1]))
