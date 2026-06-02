"""Run 5x first-chunk latency benchmark for the configured TTS adapter.

Usage:
    uv run python scripts/bench_tts_first_chunk.py
    uv run python scripts/bench_tts_first_chunk.py "다른 문장을 시험"
    uv run python scripts/bench_tts_first_chunk.py --melo

Reports the per-run latency and the mean.  Phase 3 DoD target = mean < 500ms.
"""

from __future__ import annotations

import argparse
import asyncio
import time

from app.config import load_config
from app.utils.logging import setup_logging

_DEFAULT_TEXT = "안녕하세요, 운동 시작할까요?"
_RUNS = 5


async def _bench(text: str, force_melo: bool) -> None:
    setup_logging(level="INFO")
    config = load_config()
    if force_melo:
        config = config.model_copy(
            update={"tts": config.tts.model_copy(update={"active": "melo"})}
        )

    from app.adapters.tts import get_tts_adapter

    client = get_tts_adapter(config)
    name = type(client).__name__

    print(f"\n=== {name} first-chunk benchmark ({_RUNS}x + 1 warmup) ===")
    print(f"text: {text!r}\n")

    # One untimed warmup so the first measured run is steady-state (model
    # weights paged in, kernels compiled, tokenizer cached).
    print("warmup...")
    async for _ in client.stream(text):
        break

    samples: list[float] = []
    for i in range(_RUNS):
        t0 = time.monotonic()
        async for _chunk in client.stream(text):
            ms = (time.monotonic() - t0) * 1000.0
            samples.append(ms)
            print(f"  run {i + 1}: {ms:.1f}ms")
            break
    mean = sum(samples) / len(samples)
    print(f"\nmean: {mean:.1f}ms (budget 500ms)")
    if mean >= 500.0:
        print(
            "⚠️  budget exceeded — consider switching tts.active in config.yaml "
            "or raising a follow-up ADR (ADR-006 §지연 폴백 정책)."
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("text", nargs="?", default=_DEFAULT_TEXT)
    parser.add_argument("--melo", action="store_true", help="force tts.active=melo")
    args = parser.parse_args()
    asyncio.run(_bench(args.text, args.melo))


if __name__ == "__main__":
    main()
