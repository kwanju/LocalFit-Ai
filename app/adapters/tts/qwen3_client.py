from __future__ import annotations

import asyncio
import io
import sys
import time
import wave
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

from loguru import logger

from app.config import AppConfig

_INT16_MAX = 32767  # int16 정규화 상수 (float32 [-1, 1] → int16)


@dataclass
class TTSRequest:
    text: str
    voice: str = "default"
    speed: float = 1.0


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


class Qwen3TTSClient:
    def __init__(self, config: AppConfig) -> None:
        qwen_cfg = config.tts.qwen3

        # Config validation first (before heavy imports so tests can catch errors cheaply).
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
        self._timeout_sec: float = float(qwen_cfg.get("timeout_sec", "60.0"))
        model_id: str = qwen_cfg["model_id"]
        attn_impl: str = qwen_cfg.get("attn_implementation", "sdpa")
        device_map: str = qwen_cfg.get("device_map", "cuda:0")

        import torch
        from transformers import AutoProcessor, Qwen3ForConditionalGeneration

        self._torch = torch  # 스레드에서 접근용 (asyncio.to_thread 내 사용)
        logger.info("Loading Qwen3-TTS model: {} attn={}", model_id, attn_impl)
        self._processor = AutoProcessor.from_pretrained(model_id)
        self._model = Qwen3ForConditionalGeneration.from_pretrained(
            model_id,
            attn_implementation=attn_impl,
            device_map=device_map,
            torch_dtype=torch.bfloat16,
        )
        logger.info("Qwen3-TTS model loaded: {}", model_id)

    def _synthesize_sync(self, text: str) -> tuple[np.ndarray, int]:
        t0 = time.monotonic()
        inputs = self._processor(
            text=text,
            ref_audio_path=self._ref_audio_path,
            ref_text=self._ref_text,
            return_tensors="pt",
        ).to(self._model.device)
        with self._torch.no_grad():
            output = self._model.generate(**inputs)
        audio = self._processor.decode(output[0], skip_special_tokens=True)
        sr = self._processor.feature_extractor.sampling_rate
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.info("Qwen3-TTS synthesized {} chars in {}ms", len(text), elapsed_ms)
        return audio, int(sr)

    async def synthesize(self, request: TTSRequest) -> bytes:
        try:
            audio, sample_rate = await asyncio.wait_for(
                asyncio.to_thread(self._synthesize_sync, request.text),
                timeout=self._timeout_sec,
            )
            return _float32_to_wav(audio, sample_rate)
        except TimeoutError:
            logger.warning("Qwen3-TTS synthesis timed out after {:.1f}s", self._timeout_sec)
            raise
        except Exception as e:
            logger.error("Qwen3-TTS synthesis failed: {}", e)
            raise

    async def stream(self, request: TTSRequest) -> AsyncIterator[bytes]:
        # Full synthesis first; sentence-streaming added in Phase 3 (ADR-006)
        wav_bytes = await self.synthesize(request)
        yield wav_bytes

    async def health(self) -> bool:
        return self._model is not None


async def _smoke_test(text: str) -> None:
    from app.config import load_config

    config = load_config()
    client = Qwen3TTSClient(config)

    if not await client.health():
        print("Qwen3-TTS 모델이 로드되지 않았습니다.", file=sys.stderr)
        sys.exit(1)

    request = TTSRequest(text=text)
    wav_bytes = await client.synthesize(request)

    out_path = "qwen3_smoke.wav"
    with open(out_path, "wb") as f:
        f.write(wav_bytes)
    print(f"출력: {out_path} ({len(wav_bytes)} bytes)")


if __name__ == "__main__":
    sample = sys.argv[1] if len(sys.argv) > 1 else "안녕하세요, 피트니스 코치입니다."
    asyncio.run(_smoke_test(sample))
