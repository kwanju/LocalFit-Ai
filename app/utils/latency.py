"""Latency tracker for PRD §4-1 pipeline metrics (ADR-018).

Usage:
    with LatencyTracker("tts.first_chunk"):
        ...  # measured block

Logs as `latency.<stage>=<ms>` at INFO level.
"""

from __future__ import annotations

from time import perf_counter
from types import TracebackType
from typing import Self

from loguru import logger


class LatencyTracker:
    """Context manager that emits `latency.<stage>=<ms>` on exit.

    Idempotent — calling stop() twice (or stop() then __exit__) emits once.
    """

    def __init__(self, stage: str) -> None:
        self.stage = stage
        self._t0: float = 0.0
        self._done: bool = False

    def __enter__(self) -> Self:
        self._t0 = perf_counter()
        self._done = False
        return self

    def stop(self) -> float:
        """Emit the metric early (useful for first-chunk style measurements where
        the surrounding block is still running). Returns elapsed ms."""
        if self._done:
            return 0.0
        elapsed_ms = (perf_counter() - self._t0) * 1000.0
        logger.info("latency.{}={:.1f}ms", self.stage, elapsed_ms)
        self._done = True
        return elapsed_ms

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.stop()
