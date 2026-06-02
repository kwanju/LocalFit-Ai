"""Qwen3-TTS domain adapter (ADR-006, ADR-012).

Loading
-------
Uses the upstream `qwen-tts` PyPI package (`qwen_tts.Qwen3TTSModel`).
*Not* transformers `AutoModel` — Qwen3-TTS is published as a custom class.

Streaming
---------
Upstream exposes no public token-level streaming API; every generation method
returns a full waveform.  We implement *sentence-batch* streaming (ADR-006,
2026-06-02 개정): the LLM-side caller passes a paragraph, we split on Korean
punctuation, synthesise sentence-by-sentence, and yield 16-bit PCM bytes for
each completed sentence so playback can start before later sentences finish.

Voice cloning
-------------
`create_voice_clone_prompt(ref_audio, ref_text)` is called once at __init__
and cached, so per-utterance overhead is the synthesis only.
"""

from __future__ import annotations

import asyncio
import re
import sys
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from app.config import AppConfig

if TYPE_CHECKING:
    import numpy as np

_INT16_MAX = 32767
_OUTPUT_SAMPLE_RATE = 24000  # ADR-006: Qwen3-TTS 24kHz mono

# Korean + Latin sentence-end punctuation. Split keeps the punctuation with
# the preceding sentence ("안녕하세요." not "안녕하세요").
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[\.!?。！？])\s+")


@dataclass
class TTSRequest:
    """Domain-level TTS request — Phase 1 contract preserved for callers."""

    text: str
    voice: str = "default"
    speed: float = 1.0


def _float_to_pcm16(audio: np.ndarray) -> bytes:
    """Convert a float32/float64 waveform (-1..1) to little-endian int16 PCM bytes."""
    import numpy as np

    clipped = (audio * _INT16_MAX).clip(-_INT16_MAX - 1, _INT16_MAX)
    return clipped.astype(np.int16).tobytes()


def _split_sentences(text: str) -> list[str]:
    """Split Korean text on sentence-end punctuation. Always returns ≥1 chunk."""
    pieces = [p.strip() for p in _SENTENCE_SPLIT_RE.split(text.strip()) if p.strip()]
    return pieces or [text.strip()]


# Kept for tests/api compatibility with Phase 1 contract — returns a full WAV file.
def _float32_to_wav(audio: np.ndarray, sample_rate: int) -> bytes:
    import io
    import wave

    import numpy as np

    buf = io.BytesIO()
    pcm = (audio * _INT16_MAX).clip(-_INT16_MAX - 1, _INT16_MAX).astype(np.int16)
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()


class Qwen3TTSClient:
    """Qwen3-TTS adapter — sentence-batch streaming + cached voice-clone prompt."""

    sample_rate: int = _OUTPUT_SAMPLE_RATE

    def __init__(self, config: AppConfig) -> None:
        qwen_cfg = config.tts.qwen3

        ref_audio_path = qwen_cfg.get("ref_audio_path", "")
        if not ref_audio_path:
            raise ValueError("config.yaml에 tts.qwen3.ref_audio_path를 설정해 주세요.")
        ref_file = Path(ref_audio_path)
        if not ref_file.exists():
            raise FileNotFoundError(f"참조 음성 파일을 찾을 수 없습니다: {ref_audio_path}")

        if "model_id" not in qwen_cfg:
            raise ValueError("config.yaml에 tts.qwen3.model_id를 설정해 주세요.")

        self._ref_audio_path = str(ref_file)
        self._ref_text: str = qwen_cfg.get("ref_text", "")
        self._language: str = qwen_cfg.get("language", "Korean")
        self._timeout_sec: float = float(qwen_cfg.get("timeout_sec", "60.0"))
        model_id: str = qwen_cfg["model_id"]
        attn_impl: str = qwen_cfg.get("attn_implementation", "sdpa")
        device_map: str = qwen_cfg.get("device_map", "cuda:0")

        import torch
        from qwen_tts import Qwen3TTSModel  # type: ignore[import-not-found]

        self._torch = torch
        logger.info(
            "Loading Qwen3-TTS model: {} attn={} device={}", model_id, attn_impl, device_map
        )
        try:
            self._model = Qwen3TTSModel.from_pretrained(
                model_id,
                device_map=device_map,
                dtype=torch.bfloat16,
                attn_implementation=attn_impl,
            )
        except (ValueError, RuntimeError, ImportError) as e:
            # SDPA may not be wired for every layer in some upstream versions —
            # fall back to "eager" rather than failing the whole adapter (ADR-006).
            if attn_impl == "sdpa":
                logger.warning(
                    "Qwen3-TTS sdpa load failed ({}); retrying with attn_implementation='eager'",
                    e,
                )
                self._model = Qwen3TTSModel.from_pretrained(
                    model_id,
                    device_map=device_map,
                    dtype=torch.bfloat16,
                    attn_implementation="eager",
                )
            else:
                raise

        # Cache the voice-clone prompt once — per-utterance call only does synth.
        logger.info("Computing voice-clone prompt from {}", self._ref_audio_path)
        self._voice_prompt = self._model.create_voice_clone_prompt(
            ref_audio=self._ref_audio_path,
            ref_text=self._ref_text or None,
        )
        logger.info("Qwen3-TTS ready: {} sample_rate={}", model_id, _OUTPUT_SAMPLE_RATE)

    def _synth_sentence(self, sentence: str) -> tuple[np.ndarray, int]:
        """Synchronously synthesise one sentence. Returns (float waveform, sample rate)."""
        t0 = time.monotonic()
        with self._torch.no_grad():
            wavs, sr = self._model.generate_voice_clone(
                text=sentence,
                language=self._language,
                voice_clone_prompt=self._voice_prompt,
            )
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.debug(
            "Qwen3-TTS sentence synth: '{}...' ({} chars) in {}ms",
            sentence[:30],
            len(sentence),
            elapsed_ms,
        )
        # qwen_tts returns List[np.ndarray] even for a single text (batch=1).
        return wavs[0], int(sr)

    async def stream(self, request: TTSRequest | str) -> AsyncIterator[bytes]:
        """Sentence-batch stream: yields 16-bit PCM mono bytes per sentence.

        Sample rate is `self.sample_rate` (24000 Hz). Pipecat service is
        responsible for wrapping the bytes in `TTSAudioRawFrame`.
        """
        text = request.text if isinstance(request, TTSRequest) else request
        sentences = _split_sentences(text)
        logger.debug("Qwen3-TTS stream: {} sentence(s)", len(sentences))
        for sentence in sentences:
            audio, sr = await asyncio.wait_for(
                asyncio.to_thread(self._synth_sentence, sentence),
                timeout=self._timeout_sec,
            )
            if sr != _OUTPUT_SAMPLE_RATE:
                # Sanity log — upstream is documented as 24kHz; warn if changed.
                logger.warning(
                    "Qwen3-TTS sample_rate {} != expected {}", sr, _OUTPUT_SAMPLE_RATE
                )
            yield _float_to_pcm16(audio)

    async def synthesize(self, request: TTSRequest | str) -> bytes:
        """Full-paragraph WAV synthesis (single byte blob with header).

        Kept for non-Pipecat callers (e.g. /tts REST in v1 base, smoke tests).
        Internally just concatenates the streamed sentences.
        """
        import numpy as np

        text = request.text if isinstance(request, TTSRequest) else request
        sentences = _split_sentences(text)
        pieces: list[np.ndarray] = []
        sample_rate = _OUTPUT_SAMPLE_RATE
        for sentence in sentences:
            audio, sr = await asyncio.wait_for(
                asyncio.to_thread(self._synth_sentence, sentence),
                timeout=self._timeout_sec,
            )
            sample_rate = sr
            pieces.append(audio)
        full = np.concatenate(pieces) if pieces else np.zeros(0, dtype=np.float32)
        return _float32_to_wav(full, sample_rate)

    async def health(self) -> bool:
        return self._model is not None and self._voice_prompt is not None


async def _smoke_test(text: str) -> None:
    from app.config import load_config

    config = load_config()
    client = Qwen3TTSClient(config)

    if not await client.health():
        print("Qwen3-TTS 모델이 로드되지 않았습니다.", file=sys.stderr)
        sys.exit(1)

    t0 = time.monotonic()
    chunks: list[bytes] = []
    first_chunk_ms: float | None = None
    async for chunk in client.stream(TTSRequest(text=text)):
        if first_chunk_ms is None:
            first_chunk_ms = (time.monotonic() - t0) * 1000
            print(f"first chunk: {first_chunk_ms:.1f}ms")
        chunks.append(chunk)
    total_ms = (time.monotonic() - t0) * 1000
    pcm_bytes = b"".join(chunks)
    print(f"total: {total_ms:.1f}ms  pcm_bytes={len(pcm_bytes)}")


def _is_request_like(obj: Any) -> bool:
    """Backwards-compat helper for tests."""
    return isinstance(obj, TTSRequest)


if __name__ == "__main__":
    sample = sys.argv[1] if len(sys.argv) > 1 else "안녕하세요, 운동 시작할까요?"
    asyncio.run(_smoke_test(sample))
