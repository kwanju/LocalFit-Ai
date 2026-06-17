"""Session-scoped on-demand model lifecycle (ADR-030, supersedes ADR-015).

Heavy models (STT + TTS + LLM) are **not** resident. They load when a workout/
chat session starts and unload when it ends, so idle VRAM ≈ baseline and the
user can run a game on the same GPU (v4 core requirement, 16GB baseline).

Single user (ADR-002) → at most one session at a time → one lock guards the
whole load/unload lifecycle. No multi-session bookkeeping.

Cold-start mitigation (ADR-030 (a)(b)(c)):
  (a) parallel load — STT/TTS construct on threads + LLM warmup concurrently so
      the ~30s sequential cold start collapses toward the longest stage (~15s
      TTS CUDA-graph capture). GPU spike stays < 16GB (탐사 12.2GB).
  (b) app-open prewarm — ``POST /prewarm`` calls :meth:`load` before the user
      hits 시작 (``app/api/lifecycle.py``). NOT a scheduler/background preload.
  (c) "코치 준비 중" UX — ws_voice streams a ``coach_preparing`` notice while
      this loads.

Mode note: all three models load together regardless of mode (C2C/C2S/S2S). The
parallel load makes the extra stages effectively free (TTS dominates), and
keeping them resident makes mid-session mode switches instant. Per-mode partial
loading is intentionally not implemented (YAGNI, CLAUDE.md §3).

Layer: this is an ``adapters``-layer orchestrator — it constructs the domain
adapters and reclaims CUDA memory (external-model concerns), and imports no
``core``/``pipecat``/``fastapi`` (ADR-012). ``api`` (ws_voice, /prewarm, /health)
drives it via ``app.state.models``.
"""

from __future__ import annotations

import asyncio
import gc
import time
from typing import TYPE_CHECKING

from loguru import logger

from app.config import AppConfig

if TYPE_CHECKING:
    from app.adapters.llm.ollama_client import OllamaClient
    from app.adapters.stt.faster_whisper_client import FasterWhisperClient
    from app.adapters.tts.qwen3_client import Qwen3TTSClient


class ModelLoadError(RuntimeError):
    """Heavy-model load failed (e.g. VRAM exhausted by another GPU app)."""


# 사용자 대면 한국어 (CLAUDE.md §7). VRAM 부족(타 앱 점유) 시 안 행복한 경로 (ADR-030).
MSG_VRAM_FULL: str = (
    "GPU 메모리가 부족해 코치를 켤 수 없어요. 게임이나 다른 GPU 앱을 닫고 다시 시도해 주세요."
)
MSG_LOAD_FAILED: str = "코치 모델을 불러오지 못했어요. 잠시 후 다시 시도해 주세요."


def _is_oom(err: BaseException) -> bool:
    """True if *err* looks like a CUDA out-of-memory (vs. a generic load error)."""
    name = type(err).__name__
    return name == "OutOfMemoryError" or "out of memory" in str(err).lower()


class ModelManager:
    """Loads/unloads STT+TTS+LLM on demand for the single active session."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._lock = asyncio.Lock()
        self._loaded = False
        self.llm: OllamaClient | None = None
        self.stt: FasterWhisperClient | None = None
        self.tts: Qwen3TTSClient | None = None

    @property
    def loaded(self) -> bool:
        return self._loaded

    async def load(self) -> None:
        """Parallel-load STT+TTS+LLM into VRAM. Idempotent; raises ModelLoadError.

        Concurrent callers (prewarm racing 세션 시작) serialize on the lock — the
        second sees ``_loaded`` and returns without a second load.
        """
        async with self._lock:
            if self._loaded:
                return

            from app.adapters.llm import get_llm_adapter
            from app.adapters.stt import get_stt_adapter
            from app.adapters.tts import get_tts_adapter

            logger.info("ModelManager: loading STT+TTS+LLM (on-demand, parallel) ...")
            t0 = time.monotonic()

            async def _load_llm() -> OllamaClient:
                llm = get_llm_adapter(self._config)
                await llm.warmup()  # keep_alive=config — resident for the session
                return llm

            # STT/TTS constructors are blocking (model load + CUDA-graph capture)
            # → run on threads; LLM warmup is async. gather = parallel (ADR-030 a).
            results = await asyncio.gather(
                asyncio.to_thread(get_stt_adapter, self._config),
                asyncio.to_thread(get_tts_adapter, self._config),
                _load_llm(),
                return_exceptions=True,
            )
            stt_r, tts_r, llm_r = results
            errors = [r for r in results if isinstance(r, BaseException)]
            if errors:
                # Roll back any partial load so we never leak half a session's VRAM.
                await self._discard(
                    None if isinstance(stt_r, BaseException) else stt_r,
                    None if isinstance(tts_r, BaseException) else tts_r,
                    None if isinstance(llm_r, BaseException) else llm_r,
                )
                for e in errors:
                    logger.error("ModelManager load failed: {}", e)
                message = MSG_VRAM_FULL if any(_is_oom(e) for e in errors) else MSG_LOAD_FAILED
                raise ModelLoadError(message) from errors[0]

            self.stt, self.tts, self.llm = stt_r, tts_r, llm_r  # type: ignore[assignment]
            self._loaded = True
            logger.info(
                "ModelManager: ready in {}ms (parallel load)", int((time.monotonic() - t0) * 1000)
            )

    async def unload(self) -> None:
        """Unload all models + reclaim VRAM (ADR-030 session end). Idempotent."""
        async with self._lock:
            if not self._loaded:
                return
            logger.info("ModelManager: unloading models, reclaiming VRAM ...")
            stt, tts, llm = self.stt, self.tts, self.llm
            self.stt = self.tts = self.llm = None
            self._loaded = False
            await self._discard(stt, tts, llm)
            logger.info("ModelManager: unloaded — VRAM returned to baseline")

    async def _discard(
        self,
        stt: FasterWhisperClient | None,
        tts: Qwen3TTSClient | None,
        llm: OllamaClient | None,
    ) -> None:
        """Release model objects + reclaim CUDA memory.

        ★ in-process 누수 fix: ws_voice 가 STT/TTS 어댑터를 로컬·Pipecat 서비스·pipeline·
        worker·클로저로 잡고 있어, 여기서 ``del`` + ``empty_cache`` 만 하면 어댑터 객체가
        살아남아 torch 모델이 안 풀린다(프로세스 종료 시에만 반환되던 누수). 그래서 각
        어댑터의 ``release()`` 로 **내부 무거운 모델을 직접 null** 해 참조가 남아도 VRAM 이
        회수되게 한다(spike 는 어댑터를 통째로 버려 PASS 였지만 실세션엔 참조가 남음)."""
        if llm is not None:
            await llm.unload()  # Ollama keep_alive=0
        for name, adapter in (("tts", tts), ("stt", stt)):
            if adapter is not None and hasattr(adapter, "release"):
                try:
                    adapter.release()
                except Exception as e:  # noqa: BLE001 — reclamation is best-effort
                    logger.warning("{} release failed: {}", name, e)
        del stt, tts, llm
        gc.collect()
        self._empty_cuda_cache()

    @staticmethod
    def _empty_cuda_cache() -> None:
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
        except Exception as e:  # noqa: BLE001 — reclamation is best-effort
            logger.warning("torch.cuda.empty_cache failed: {}", e)
