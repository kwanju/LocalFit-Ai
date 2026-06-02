"""tests/unit/test_interrupt_pause.py — 인터럽트/일시정지 키워드 동작 검증
(phase-6 §6-4 / §6-7).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from pipecat.frames.frames import TranscriptionFrame
from pipecat.tests.utils import run_test

from app.pipecat_services.processors.safety_guard import SafetyGuardProcessor


async def _drive(proc, frames):
    down, _ = await run_test(proc, frames_to_send=frames)
    return list(down)


# --- Pause keyword tests ---

async def test_pause_keyword_calls_manager_pause() -> None:
    """'그만' in transcript must call counting_manager.pause()."""
    manager = MagicMock()
    manager.pause = AsyncMock()
    safety = SafetyGuardProcessor(counting_manager=manager)

    await _drive(safety, [TranscriptionFrame(text="그만요", user_id="", timestamp="")])
    manager.pause.assert_awaited_once()


async def test_pause_keyword_frame_still_forwarded() -> None:
    """After pause, the frame must still reach downstream (LLM responds naturally)."""
    manager = MagicMock()
    manager.pause = AsyncMock()
    safety = SafetyGuardProcessor(counting_manager=manager)

    down = await _drive(safety, [TranscriptionFrame(text="잠깐만요", user_id="", timestamp="")])
    texts = [f.text for f in down if isinstance(f, TranscriptionFrame)]
    assert "잠깐만요" in texts


async def test_pause_keyword_멈춰() -> None:
    manager = MagicMock()
    manager.pause = AsyncMock()
    safety = SafetyGuardProcessor(counting_manager=manager)

    await _drive(safety, [TranscriptionFrame(text="멈춰", user_id="", timestamp="")])
    manager.pause.assert_awaited_once()


async def test_no_pause_without_manager() -> None:
    """Without counting_manager, pause keywords do NOT raise."""
    safety = SafetyGuardProcessor()
    down = await _drive(safety, [TranscriptionFrame(text="그만", user_id="", timestamp="")])
    # Frame passes through
    assert any(isinstance(f, TranscriptionFrame) for f in down)


async def test_non_pause_keyword_no_pause_call() -> None:
    """Normal user text must NOT trigger pause."""
    manager = MagicMock()
    manager.pause = AsyncMock()
    safety = SafetyGuardProcessor(counting_manager=manager)

    await _drive(safety, [TranscriptionFrame(text="오늘 날씨 좋네요", user_id="", timestamp="")])
    manager.pause.assert_not_awaited()


# --- Injury keyword → stop counting ---

async def test_injury_keyword_stops_counting() -> None:
    """Injury keyword must call counting_manager.stop() in addition to safety bypass."""
    manager = MagicMock()
    manager.stop = AsyncMock()
    manager.pause = AsyncMock()
    safety = SafetyGuardProcessor(counting_manager=manager)

    await _drive(safety, [TranscriptionFrame(text="무릎이 아파요", user_id="", timestamp="")])
    manager.stop.assert_awaited_once()


async def test_injury_keyword_bypasses_llm() -> None:
    """Safety bypass response must appear when injury keyword is present."""
    from app.pipecat_services.frames import SafetyResponseFrame

    manager = MagicMock()
    manager.stop = AsyncMock()
    manager.pause = AsyncMock()
    safety = SafetyGuardProcessor(counting_manager=manager)

    down = await _drive(
        safety, [TranscriptionFrame(text="허리가 아파요", user_id="", timestamp="")]
    )
    assert any(isinstance(f, SafetyResponseFrame) for f in down)


async def test_pause_exception_does_not_break_pipeline() -> None:
    """Exception in counting_manager.pause must be swallowed."""
    manager = MagicMock()
    manager.pause = AsyncMock(side_effect=RuntimeError("engine gone"))
    safety = SafetyGuardProcessor(counting_manager=manager)

    # Must not raise
    down = await _drive(safety, [TranscriptionFrame(text="그만", user_id="", timestamp="")])
    assert any(isinstance(f, TranscriptionFrame) for f in down)
