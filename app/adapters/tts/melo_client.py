"""MeloTTS domain adapter — Korean preset speaker (ADR-006, 2026-06-02 개정).

Sentence-batch streaming via MeloTTS's own `split_sentences_into_pieces` +
per-sentence `tts_to_file(output_path=None)` calls (which return a numpy
waveform directly).  No voice cloning — preset speaker only.

Why a separate adapter when Qwen3-TTS exists?
  See ADR-006 — Melo's much-lower expected latency (<100ms first chunk on GPU)
  and MIT licence are valuable as a fallback / A-B comparison option.  Active
  adapter is chosen by `config.tts.active`.
"""

from __future__ import annotations

import asyncio
import sys
import time
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from loguru import logger

from app.adapters.tts.qwen3_client import TTSRequest, _float32_to_wav, _float_to_pcm16
from app.config import AppConfig

if TYPE_CHECKING:
    import numpy as np


def _install_japanese_mecab_stub() -> None:
    """melo.text.japanese does ``import MeCab`` then ``_TAGGER = MeCab.Tagger()``
    at module load.  We only use Korean — install a no-op stub so the import
    succeeds without requiring the Windows-broken mecab-python3 wheel."""
    import sys as _sys
    import types as _types

    if "MeCab" in _sys.modules:
        return

    class _StubTagger:
        def __init__(self, *_a, **_kw) -> None:
            pass

        def parse(self, _text: str) -> str:
            return ""

        def parseToNode(self, _text: str):
            return None

    stub = _types.ModuleType("MeCab")
    stub.Tagger = _StubTagger  # type: ignore[attr-defined]
    _sys.modules["MeCab"] = stub


def _patch_g2pkk_for_windows() -> None:
    """g2pkk's `get_mecab()` on Windows hard-codes ``eunjeon`` (requires MSVC
    build of mecab-ko).  python-mecab-ko ships a prebuilt Windows wheel under
    the ``mecab`` module — swap that in so Korean G2P works without MSVC."""
    try:
        import g2pkk.g2pkk as _g2pkk  # type: ignore[import-untyped]
        from mecab import MeCab as _MeCab  # type: ignore[import-untyped]

        def _patched_get_mecab(self):  # noqa: ANN001 — match upstream signature
            return _MeCab()

        _g2pkk.G2p.get_mecab = _patched_get_mecab
    except ImportError as e:
        logger.warning("Korean MeCab patch skipped (missing package: {})", e)


class MeloTTSClient:
    """MeloTTS adapter — Korean preset speaker, sentence-batch streaming."""

    def __init__(self, config: AppConfig) -> None:
        melo_cfg = config.tts.melo
        if not melo_cfg:
            raise ValueError("config.yaml에 tts.melo 섹션이 비어 있습니다.")

        language: str = melo_cfg.get("language", "KR")
        device: str = melo_cfg.get("device", "cuda:0")
        self._speaker_id: int = int(melo_cfg.get("speaker_id", "0"))
        self._speed: float = float(melo_cfg.get("speed", "1.0"))
        self._timeout_sec: float = float(melo_cfg.get("timeout_sec", "30.0"))

        logger.info("Loading MeloTTS model: language={} device={}", language, device)
        _install_japanese_mecab_stub()
        _patch_g2pkk_for_windows()
        from melo.api import TTS  # type: ignore[import-not-found]

        self._model = TTS(language=language, device=device)
        self.sample_rate: int = int(self._model.hps.data.sampling_rate)
        logger.info(
            "MeloTTS ready: language={} sample_rate={} speaker_id={}",
            language,
            self.sample_rate,
            self._speaker_id,
        )

    def _synth_sentence(self, sentence: str) -> np.ndarray:
        t0 = time.monotonic()
        audio = self._model.tts_to_file(
            text=sentence,
            speaker_id=self._speaker_id,
            output_path=None,         # ← returns numpy waveform directly
            speed=self._speed,
            quiet=True,
        )
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.debug(
            "MeloTTS sentence synth: '{}...' ({} chars) in {}ms",
            sentence[:30],
            len(sentence),
            elapsed_ms,
        )
        return audio

    def _split(self, text: str) -> list[str]:
        # Use MeloTTS's own splitter so the sentence boundaries match the
        # tokeniser/G2P assumptions (handles Korean punctuation natively).
        pieces = self._model.split_sentences_into_pieces(text, self._model.language, quiet=True)
        return [p for p in pieces if p.strip()] or [text.strip()]

    async def stream(self, request: TTSRequest | str) -> AsyncIterator[bytes]:
        """Yield 16-bit PCM mono bytes per sentence (sample rate = self.sample_rate)."""
        text = request.text if isinstance(request, TTSRequest) else request
        sentences = self._split(text)
        logger.debug("MeloTTS stream: {} sentence(s)", len(sentences))
        for sentence in sentences:
            audio = await asyncio.wait_for(
                asyncio.to_thread(self._synth_sentence, sentence),
                timeout=self._timeout_sec,
            )
            yield _float_to_pcm16(audio)

    async def synthesize(self, request: TTSRequest | str) -> bytes:
        """Full-paragraph WAV (with header) — convenience for non-Pipecat callers."""
        import numpy as np

        text = request.text if isinstance(request, TTSRequest) else request
        sentences = self._split(text)
        pieces: list[np.ndarray] = []
        for sentence in sentences:
            audio = await asyncio.wait_for(
                asyncio.to_thread(self._synth_sentence, sentence),
                timeout=self._timeout_sec,
            )
            pieces.append(audio)
        full = np.concatenate(pieces) if pieces else np.zeros(0, dtype=np.float32)
        return _float32_to_wav(full, self.sample_rate)

    async def health(self) -> bool:
        return self._model is not None


def _is_request_like(obj: Any) -> bool:
    return isinstance(obj, TTSRequest)


async def _smoke_test(text: str) -> None:
    from app.config import load_config

    config = load_config()
    client = MeloTTSClient(config)

    if not await client.health():
        print("MeloTTS 모델이 로드되지 않았습니다.", file=sys.stderr)
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
    print(f"total: {total_ms:.1f}ms  pcm_bytes={len(pcm_bytes)}  sr={client.sample_rate}")


if __name__ == "__main__":
    sample = sys.argv[1] if len(sys.argv) > 1 else "안녕하세요, 운동 시작할까요?"
    asyncio.run(_smoke_test(sample))
