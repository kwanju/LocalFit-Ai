from __future__ import annotations

import asyncio
import io
import logging
import sys
import time
import wave
from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

from app.adapters.tts.protocol import TTSRequest
from app.config import AppConfig

logger = logging.getLogger(__name__)

_INT16_MAX = 32767  # int16 정규화 상수 (float32 [-1, 1] → int16)


def _float32_to_wav(audio: np.ndarray, sample_rate: int) -> bytes:
    """Convert float32 numpy array to 16-bit mono WAV bytes."""
    import numpy as np

    buf = io.BytesIO()
    pcm = (audio * _INT16_MAX).clip(-_INT16_MAX - 1, _INT16_MAX).astype(np.int16)
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()


class Qwen3TTSAdapter:
    def __init__(self, config: AppConfig) -> None:
        import torch
        from qwen_tts import Qwen3TTSModel

        qwen_cfg = config.tts.qwen3

        ref_audio_path = qwen_cfg.get("ref_audio_path", "")
        if not ref_audio_path:
            raise ValueError("config.yaml에 tts.qwen3.ref_audio_path를 설정해 주세요.")

        ref_file = Path(ref_audio_path)
        if not ref_file.exists():
            raise FileNotFoundError(f"참조 음성 파일을 찾을 수 없습니다: {ref_audio_path}")

        self._ref_audio_path = str(ref_file)
        self._ref_text: str = qwen_cfg.get("ref_text", "")
        self._timeout_sec: float = float(qwen_cfg.get("timeout_sec", "60.0"))
        model_id: str = qwen_cfg.get("model_id", "Qwen/Qwen3-TTS-12Hz-1.7B-Base")

        logger.info("Loading Qwen3-TTS model: %s", model_id)
        self._model = Qwen3TTSModel.from_pretrained(
            model_id,
            device_map="cuda:0",
            dtype=torch.bfloat16,
        )
        logger.info("Qwen3-TTS model loaded: %s", model_id)

    def _synthesize_sync(self, text: str) -> tuple:
        t0 = time.monotonic()
        wavs, sr = self._model.generate_voice_clone(
            text=text,
            language="Korean",
            ref_audio=self._ref_audio_path,
            ref_text=self._ref_text,
        )
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.info("Qwen3-TTS synthesized %d chars in %dms", len(text), elapsed_ms)
        return wavs[0], int(sr)

    async def synthesize(self, request: TTSRequest) -> bytes:
        try:
            audio, sample_rate = await asyncio.wait_for(
                asyncio.to_thread(self._synthesize_sync, request.text),
                timeout=self._timeout_sec,
            )
            return _float32_to_wav(audio, sample_rate)
        except TimeoutError:
            logger.warning("Qwen3-TTS synthesis timed out after %.1fs", self._timeout_sec)
            raise
        except Exception as e:
            logger.error("Qwen3-TTS synthesis failed: %s", e)
            raise

    async def stream(self, request: TTSRequest) -> AsyncIterator[bytes]:
        # Qwen3-TTS has no native streaming — yield full audio as one chunk
        wav_bytes = await self.synthesize(request)
        yield wav_bytes

    async def health(self) -> bool:
        return self._model is not None


async def _smoke_test(text: str) -> None:
    from app.config import load_config

    config = load_config()
    adapter = Qwen3TTSAdapter(config)

    if not await adapter.health():
        print("Qwen3-TTS 모델이 로드되지 않았습니다.", file=sys.stderr)
        sys.exit(1)

    request = TTSRequest(text=text)
    wav_bytes = await adapter.synthesize(request)

    out_path = "qwen3_smoke.wav"
    with open(out_path, "wb") as f:
        f.write(wav_bytes)
    print(f"출력: {out_path} ({len(wav_bytes)} bytes)")


if __name__ == "__main__":
    sample = sys.argv[1] if len(sys.argv) > 1 else "안녕하세요, 피트니스 코치입니다."
    asyncio.run(_smoke_test(sample))
