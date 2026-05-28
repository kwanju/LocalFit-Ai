import asyncio
import time
from collections.abc import Awaitable, Callable


async def beat_scheduler(
    interval_sec: float,
    callback: Callable[[], Awaitable[None]],
) -> None:
    """Absolute-time beat scheduler — no drift accumulation.

    Uses time.monotonic() reference instead of accumulating sleep durations.
    Run as an asyncio.Task; cancel the task to stop.
    """
    next_beat = time.monotonic()
    while True:
        await callback()
        next_beat += interval_sec
        await asyncio.sleep(max(0.0, next_beat - time.monotonic()))
