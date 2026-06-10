"""Phase v4-0 S-8 — on-demand model VRAM lifecycle spike (ADR-030).

Measures whether STT + TTS + LLM VRAM is actually *returned* after a simulated
session ends, and records the cold-start load time. This is the ★ gate that
decides ADR-030 (on-demand load/unload, supersedes ADR-015's 24h residency).

NOT wired into Pipecat — it drives the domain adapters directly so the
measurement is isolated and repeatable (회고 4-3).

Run on as-clean-a-GPU-as-possible (close games/other GPU apps) so the device
free/total reading reflects our models, not background apps:

    uv run python -m scripts.spike_vram_lifecycle

Reads model names from config.yaml (so it matches whatever is actually pulled).
"""

from __future__ import annotations

import asyncio
import gc
import time


def _vram() -> tuple[int, int, int, int, int]:
    """Return device VRAM (MiB): free, total, used, torch_allocated, torch_reserved."""
    import torch

    free, total = torch.cuda.mem_get_info()  # whole device, all processes
    alloc = torch.cuda.memory_allocated()
    reserved = torch.cuda.memory_reserved()
    mb = 1024 * 1024
    return free // mb, total // mb, (total - free) // mb, alloc // mb, reserved // mb


def _report(label: str) -> None:
    free, total, used, alloc, reserved = _vram()
    print(
        f"[{label:<22}] device used={used:>6} MiB / {total} MiB "
        f"(free={free}) | torch alloc={alloc} reserved={reserved}",
        flush=True,
    )


async def main() -> None:
    import torch

    from app.adapters.llm.ollama_client import LLMMessage, LLMRequest, OllamaClient
    from app.adapters.stt.faster_whisper_client import FasterWhisperClient
    from app.adapters.tts.qwen3_client import Qwen3TTSClient, TTSRequest
    from app.config import load_config

    config = load_config()
    print(
        f"models: llm={config.llm.model} "
        f"stt={config.stt.model} tts={config.tts.qwen3.get('model_id', '?')}\n",
        flush=True,
    )

    _report("baseline (no models)")

    # ---- session start: load STT + TTS + LLM (cold start) ----
    t0 = time.monotonic()

    stt = FasterWhisperClient(config)
    _report("after STT load")

    tts = Qwen3TTSClient(config)
    _report("after TTS load")

    llm = OllamaClient(config)
    await llm.warmup()  # 120s timeout — survives a cold 9b load (config timeout_sec is short)
    coldstart_ms = int((time.monotonic() - t0) * 1000)
    _report("after LLM load (session)")
    print(f"\n>>> COLD START (STT+TTS+LLM ready): {coldstart_ms} ms\n", flush=True)

    # one real inference each, so the measurement reflects active-session VRAM
    await stt.transcribe(b"\x00\x00" * 16000)  # 1s silence @16kHz
    async for _ in tts.stream(TTSRequest(text="좋아요, 시작할게요.")):
        pass
    await llm.generate(
        LLMRequest(messages=[LLMMessage(role="user", content="한 문장으로 격려해줘")], keep_alive="10m")
    )
    _report("after 1 inference each")

    # ---- session end: unload everything, expect VRAM to return ----
    print("\n--- unloading (session end) ---", flush=True)
    tu = time.monotonic()

    # LLM: ask Ollama to drop the model from VRAM immediately.
    await llm.generate(
        LLMRequest(messages=[LLMMessage(role="user", content="안녕")], max_tokens=1, keep_alive="0s")
    )

    # STT (CTranslate2) + TTS (torch): drop references, then reclaim.
    if hasattr(tts, "_executor"):
        tts._executor.shutdown(wait=True)
    del stt, tts, llm
    gc.collect()
    torch.cuda.empty_cache()
    torch.cuda.synchronize()

    # Ollama unload + driver reclaim are async — poll for a few seconds.
    for i in range(1, 7):
        await asyncio.sleep(1.0)
        _report(f"after unload +{i}s")

    print(f"\n>>> unload settle window: {int((time.monotonic() - tu) * 1000)} ms", flush=True)
    print(
        "\nPASS if 'after unload' device-used returns close to baseline "
        "(LLM + STT + TTS freed). Note any residual MiB that never releases.",
        flush=True,
    )


if __name__ == "__main__":
    asyncio.run(main())
