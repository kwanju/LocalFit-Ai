"""Qwen3-TTS domain adapter (ADR-006, ADR-012).

Loading
-------
Uses the `faster-qwen3-tts` PyPI package (`faster_qwen3_tts.FasterQwen3TTS`),
a CUDA-Graph-accelerated backend for the same `Qwen3-TTS-12Hz-1.7B-Base`
weights.  TTFA drops from ~5.5s (upstream `qwen-tts`) to ~1s (sentence-batch)
on RTX 5090 (ADR-006, 2026-06-07 개정).

Streaming
---------
*Token-level* streaming (ADR-006 §후속, 2026-06-08): `stream()` drives
`generate_voice_clone_streaming` so the first audio chunk arrives mid-utterance
(TTFA ~390ms vs ~880ms sentence-batch).  The upstream generator is sync, so we
run it on a worker thread and bridge chunks to the async generator via a
thread-safe queue.  `synthesize()` (full-WAV, non-Pipecat) keeps the
sentence-batch path via `_synth_sentence`.

Voice cloning
-------------
`FasterQwen3TTS` caches the extracted voice-clone prompt internally, keyed by
`(ref_audio, ref_text, ...)`.  We pass `ref_audio`/`ref_text` on every call;
the first one extracts + caches, the rest reuse.  A throwaway warmup synth runs
at __init__ so the CUDA-graph capture (~7s) happens at startup, not on the
user's first utterance.
"""

from __future__ import annotations

import asyncio
import re
import sys
import time
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
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
    """Qwen3-TTS adapter — token-level streaming + cached voice-clone prompt."""

    sample_rate: int = _OUTPUT_SAMPLE_RATE

    def __init__(self, config: AppConfig) -> None:
        qwen_cfg = config.tts.qwen3
        self._ref_audio_path, self._ref_text, model_id, attn_impl, device = (
            self._validate_config(qwen_cfg)
        )
        self._language: str = qwen_cfg.get("language", "Korean")
        self._timeout_sec: float = float(qwen_cfg.get("timeout_sec", "30.0"))
        # token-level streaming chunk size (ADR-006 §후속): smaller → lower TTFA,
        # more (smaller) frames.  12 ≈ first chunk ~390ms on RTX 5090.
        self._chunk_size: int = int(qwen_cfg.get("chunk_size", "12"))
        self._gen_kwargs = self._build_gen_kwargs(qwen_cfg)
        self._model, self._torch = self._load_model(model_id, attn_impl, device)
        # ALL torch/CUDA generation runs on this single dedicated thread so the
        # CUDA graphs (captured during warmup) are reused — running generation on
        # varying executor threads recaptured the graph every call and TTFA blew
        # up 390ms→5800ms (2026-06-08 verification).  One thread = one CUDA stream.
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="qwen3-tts")
        self._ready = False
        self._executor.submit(self._warmup).result()
        logger.info("Qwen3-TTS ready: {} sample_rate={}", model_id, _OUTPUT_SAMPLE_RATE)

    @staticmethod
    def _validate_config(qwen_cfg: dict) -> tuple[str, str, str, str, str]:
        """Validate the `tts.qwen3` config dict and return the fields needed for load."""
        ref_audio_path = qwen_cfg.get("ref_audio_path", "")
        if not ref_audio_path:
            raise ValueError("config.yaml에 tts.qwen3.ref_audio_path를 설정해 주세요.")
        ref_file = Path(ref_audio_path)
        if not ref_file.exists():
            raise FileNotFoundError(f"참조 음성 파일을 찾을 수 없습니다: {ref_audio_path}")
        if "model_id" not in qwen_cfg:
            raise ValueError("config.yaml에 tts.qwen3.model_id를 설정해 주세요.")
        # `device` is the faster-qwen3-tts arg; accept legacy `device_map` key too.
        device = qwen_cfg.get("device") or qwen_cfg.get("device_map", "cuda:0")
        return (
            str(ref_file),
            qwen_cfg.get("ref_text", ""),
            qwen_cfg["model_id"],
            qwen_cfg.get("attn_implementation", "sdpa"),
            device,
        )

    @staticmethod
    def _build_gen_kwargs(qwen_cfg: dict) -> dict:
        """Generation params for voice-clone stability (ADR-006 2026-06-07/08).

        faster-qwen3-tts defaults (temperature=0.9, top_k=50, do_sample=True) make
        each independent synth stochastic — short cues ("둘!") and even whole
        sentences drift in timbre so the cloned voice sounds like a different
        person each time.  Two levers, both config-overridable:
          * do_sample=False (greedy) — deterministic acoustic tokens.
          * xvec_only=True — clone via a fixed speaker x-vector instead of ICL
            (acoustic-context) mode.  ICL is more faithful but its per-utterance
            conditioning is the main source of timbre drift; the x-vector pins one
            consistent speaker identity (2026-06-08, "목소리가 전부 달라" fix).
        """
        return {
            "temperature": float(qwen_cfg.get("temperature", "0.7")),
            "top_k": int(qwen_cfg.get("top_k", "40")),
            "top_p": float(qwen_cfg.get("top_p", "0.95")),
            "repetition_penalty": float(qwen_cfg.get("repetition_penalty", "1.05")),
            "do_sample": str(qwen_cfg.get("do_sample", "true")).lower() != "false",
            "xvec_only": str(qwen_cfg.get("xvec_only", "false")).lower() == "true",
        }

    @staticmethod
    def _load_model(model_id: str, attn_impl: str, device: str):
        """Load FasterQwen3TTS with sdpa→eager fallback (ADR-006).  Returns (model, torch)."""
        import torch
        from faster_qwen3_tts import FasterQwen3TTS  # type: ignore[import-not-found]

        logger.info(
            "Loading faster-qwen3-tts model: {} attn={} device={}", model_id, attn_impl, device
        )
        try:
            model = FasterQwen3TTS.from_pretrained(
                model_id,
                device=device,
                dtype=torch.bfloat16,
                attn_implementation=attn_impl,
            )
        except (ValueError, RuntimeError, ImportError) as e:
            if attn_impl != "sdpa":
                raise
            logger.warning(
                "faster-qwen3-tts sdpa load failed ({}); retrying with attn_implementation='eager'",
                e,
            )
            model = FasterQwen3TTS.from_pretrained(
                model_id,
                device=device,
                dtype=torch.bfloat16,
                attn_implementation="eager",
            )
        return model, torch

    def _warmup(self) -> None:
        """Trigger CUDA-graph capture + voice-prompt extraction at startup.

        Warms the *streaming* path (the hot path used by `stream()`): the first
        `generate_voice_clone_streaming` call captures CUDA graphs (~7s) and
        extracts the voice-clone prompt from the reference audio, so the user's
        first real utterance is fast and the model's internal
        `_voice_prompt_cache` for `(ref_audio, ref_text)` is populated.
        """
        logger.info("Warming up faster-qwen3-tts (CUDA graph + voice prompt) ...")
        t0 = time.monotonic()
        with self._torch.no_grad():
            for _chunk, _sr, _timing in self._model.generate_voice_clone_streaming(
                text="안녕하세요.",
                language=self._language,
                ref_audio=self._ref_audio_path,
                ref_text=self._ref_text,
                chunk_size=self._chunk_size,
                **self._gen_kwargs,
            ):
                pass
        self._ready = True
        logger.info("faster-qwen3-tts warmup done in {}ms", int((time.monotonic() - t0) * 1000))

    def _synth_sentence(self, sentence: str) -> tuple[np.ndarray, int]:
        """Synchronously synthesise one sentence. Returns (float waveform, sample rate)."""
        t0 = time.monotonic()
        with self._torch.no_grad():
            wavs, sr = self._model.generate_voice_clone(
                text=sentence,
                language=self._language,
                ref_audio=self._ref_audio_path,
                ref_text=self._ref_text,
                **self._gen_kwargs,
            )
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.debug(
            "faster-qwen3-tts sentence synth: '{}...' ({} chars) in {}ms",
            sentence[:30],
            len(sentence),
            elapsed_ms,
        )
        # generate_voice_clone returns (List[np.ndarray], sr) — batch=1 here.
        return wavs[0], int(sr)

    async def stream(self, request: TTSRequest | str) -> AsyncIterator[bytes]:
        """Token-level stream: yields 16-bit PCM mono bytes as the model emits them.

        Uses `generate_voice_clone_streaming` so the first audio chunk arrives
        before the full utterance is synthesised (TTFA ~390ms vs ~880ms
        sentence-batch, ADR-006 §후속).  The upstream generator is synchronous, so
        we drive it on a worker thread and bridge chunks to this async generator
        via a thread-safe queue.  Sample rate is `self.sample_rate` (24000 Hz);
        the Pipecat service wraps the bytes in `TTSAudioRawFrame`.
        """
        text = (request.text if isinstance(request, TTSRequest) else request).strip()
        if not text:
            return

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[bytes | object] = asyncio.Queue()
        sentinel = object()
        error_box: list[BaseException] = []

        def _produce() -> None:
            try:
                with self._torch.no_grad():
                    for chunk, sr, _timing in self._model.generate_voice_clone_streaming(
                        text=text,
                        language=self._language,
                        ref_audio=self._ref_audio_path,
                        ref_text=self._ref_text,
                        chunk_size=self._chunk_size,
                        **self._gen_kwargs,
                    ):
                        if sr != _OUTPUT_SAMPLE_RATE:
                            logger.warning(
                                "Qwen3-TTS sample_rate {} != expected {}", sr, _OUTPUT_SAMPLE_RATE
                            )
                        loop.call_soon_threadsafe(queue.put_nowait, _float_to_pcm16(chunk))
            except BaseException as e:  # noqa: BLE001 — surfaced to the consumer below
                error_box.append(e)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, sentinel)

        t0 = time.monotonic()
        fut = loop.run_in_executor(self._executor, _produce)
        first = True
        while True:
            # Per-chunk gap timeout — chunks normally arrive every ~50-200ms.
            item = await asyncio.wait_for(queue.get(), timeout=self._timeout_sec)
            if item is sentinel:
                break
            if first:
                logger.debug(
                    "Qwen3-TTS stream first chunk: '{}...' in {}ms",
                    text[:30], int((time.monotonic() - t0) * 1000),
                )
                first = False
            yield item  # type: ignore[misc]

        await fut
        if error_box:
            raise error_box[0]

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
        loop = asyncio.get_running_loop()
        for sentence in sentences:
            # Same dedicated executor as stream() — keep all CUDA work on one thread.
            audio, sr = await asyncio.wait_for(
                loop.run_in_executor(self._executor, self._synth_sentence, sentence),
                timeout=self._timeout_sec,
            )
            sample_rate = sr
            pieces.append(audio)
        full = np.concatenate(pieces) if pieces else np.zeros(0, dtype=np.float32)
        return _float32_to_wav(full, sample_rate)

    async def health(self) -> bool:
        return self._model is not None and self._ready


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
