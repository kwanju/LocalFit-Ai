"""FasterWhisperClient — domain STT adapter (ADR-005, ADR-012).

Forces all audio to 16kHz at the entry point via `librosa.resample` to avoid the
v1 known issue where 32kHz input produced transcript misalignment (ADR-005 §결정).
"""

import asyncio
import io
import sys
import time
import wave
from dataclasses import dataclass

import numpy as np
from faster_whisper import WhisperModel
from loguru import logger

from app.config import AppConfig

_INT16_SCALE = 32768.0  # 2^15: int16 → float32 정규화 상수
_TARGET_SR = 16000      # ADR-005: faster-whisper는 16kHz를 가정


@dataclass
class STTResult:
    text: str
    language: str
    duration_ms: int


def _decode_audio(audio_bytes: bytes) -> tuple[np.ndarray, int]:
    """Decode WAV bytes or raw int16 PCM bytes → (float32 mono array, src sample rate).

    Raw (header-less) bytes are assumed to be at the target sample rate; resampling
    only triggers when the WAV header reports a different rate.
    """
    if audio_bytes[:4] == b"RIFF":
        with wave.open(io.BytesIO(audio_bytes)) as wf:
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            src_sr = wf.getframerate()
            raw = wf.readframes(wf.getnframes())
        if sampwidth != 2:
            raise ValueError(f"Unsupported PCM sample width: {sampwidth} bytes (expected 2)")
        pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / _INT16_SCALE
        if n_channels > 1:
            pcm = pcm.reshape(-1, n_channels).mean(axis=1)
        return pcm, src_sr
    return np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / _INT16_SCALE, _TARGET_SR


def _ensure_16k(audio: np.ndarray, src_sr: int, target_sr: int) -> np.ndarray:
    """Resample to `target_sr` if needed. Logs latency for the 5ms budget check."""
    if src_sr == target_sr:
        return audio
    # librosa is in the [gpu] extras alongside faster-whisper, so importing here
    # keeps the unit-test path (which only uses _decode_audio) librosa-free.
    import librosa

    t0 = time.monotonic()
    resampled = librosa.resample(audio, orig_sr=src_sr, target_sr=target_sr)
    elapsed_ms = (time.monotonic() - t0) * 1000.0
    logger.info(
        "latency.stt.resample={:.1f}ms src_sr={} target_sr={} samples={}",
        elapsed_ms,
        src_sr,
        target_sr,
        len(audio),
    )
    return resampled


class FasterWhisperClient:
    def __init__(self, config: AppConfig) -> None:
        cfg = config.stt
        self._lang: str = cfg.language
        self._timeout_sec: float = cfg.timeout_sec
        self._beam_size: int = cfg.beam_size
        self._vad_filter: bool = cfg.vad_filter
        self._target_sr: int = cfg.resample_to
        logger.info(
            "Loading faster-whisper model={} device={} compute_type={} beam_size={} vad_filter={}",
            cfg.model,
            cfg.device,
            cfg.compute_type,
            cfg.beam_size,
            cfg.vad_filter,
        )
        self._model = WhisperModel(cfg.model, device=cfg.device, compute_type=cfg.compute_type)
        logger.info("faster-whisper model loaded: {}", cfg.model)
        # Eager librosa import: pay the ~1.5s import once at lifespan startup so
        # first 32kHz transcription doesn't blow the per-request budget.
        import librosa  # noqa: F401

    @property
    def target_sample_rate(self) -> int:
        return self._target_sr

    def _transcribe_sync(self, audio: np.ndarray) -> STTResult:
        t0 = time.monotonic()
        segments_gen, info = self._model.transcribe(
            audio,
            language=self._lang,
            beam_size=self._beam_size,
            vad_filter=self._vad_filter,
        )
        parts = [seg.text.strip() for seg in segments_gen]
        text = " ".join(p for p in parts if p).strip()
        duration_ms = int((time.monotonic() - t0) * 1000)
        return STTResult(text=text, language=info.language, duration_ms=duration_ms)

    async def transcribe(self, audio_bytes: bytes, sample_rate: int | None = None) -> STTResult:
        """Transcribe Korean speech. Forces 16kHz via librosa if input differs.

        Args:
            audio_bytes: WAV (RIFF) or raw int16 PCM mono bytes.
            sample_rate: Optional override for header-less raw PCM. Ignored for WAV
                inputs (header is authoritative).
        """
        try:
            audio, header_sr = _decode_audio(audio_bytes)
            src_sr = header_sr if audio_bytes[:4] == b"RIFF" else (sample_rate or header_sr)
            audio = _ensure_16k(audio, src_sr, self._target_sr)
            result = await asyncio.wait_for(
                asyncio.to_thread(self._transcribe_sync, audio),
                timeout=self._timeout_sec,
            )
            logger.info(
                "latency.stt.transcribe={}ms chars={}",
                result.duration_ms,
                len(result.text),
            )
            return result
        except TimeoutError:
            logger.warning("STT transcription timed out after {:.1f}s", self._timeout_sec)
            raise
        except Exception as e:
            logger.error("STT transcription failed: {}", e)
            raise

    async def health(self) -> bool:
        return self._model is not None


async def _smoke_test(audio_path: str) -> None:
    from app.config import load_config

    config = load_config()
    client = FasterWhisperClient(config)

    if not await client.health():
        print("FasterWhisper 모델이 로드되지 않았습니다.", file=sys.stderr)
        sys.exit(1)

    with open(audio_path, "rb") as f:
        audio_bytes = f.read()

    result = await client.transcribe(audio_bytes)
    print(f"텍스트: {result.text}")
    print(f"언어: {result.language}")
    print(f"처리 시간: {result.duration_ms}ms")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python -m app.adapters.stt.faster_whisper_client <audio.wav>",
              file=sys.stderr)
        sys.exit(1)
    asyncio.run(_smoke_test(sys.argv[1]))
