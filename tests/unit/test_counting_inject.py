"""tests/unit/test_counting_inject.py — beat → TextFrame 변환 (phase-6 §6-7)."""

import asyncio

from pipecat.frames.frames import TextFrame

from app.core.counting import BeatEvent, CountingEngine, ExerciseMode
from app.pipecat_services.processors.counting_inject import CountingInjectProcessor


async def test_inject_beat_pushes_text_frame() -> None:
    """Non-empty cue in BeatEvent must result in TextFrame pushed downstream."""
    inject_proc = CountingInjectProcessor()
    captured: list[TextFrame] = []

    async def mock_push(frame, direction=None) -> None:
        if isinstance(frame, TextFrame):
            captured.append(frame)

    inject_proc.push_frame = mock_push

    event = BeatEvent(rep=0, phase="up", elapsed_sec=0.0, cue="올라가요!")
    await inject_proc._inject_beat(event)

    assert len(captured) == 1
    assert captured[0].text == "올라가요!"


async def test_inject_beat_empty_cue_skipped() -> None:
    """Empty cue must NOT produce a TextFrame."""
    inject_proc = CountingInjectProcessor()
    captured: list[TextFrame] = []

    async def mock_push(frame, direction=None) -> None:
        if isinstance(frame, TextFrame):
            captured.append(frame)

    inject_proc.push_frame = mock_push

    event = BeatEvent(rep=0, phase="up", elapsed_sec=0.0, cue="")
    await inject_proc._inject_beat(event)

    assert captured == []


async def test_attach_engine_wires_on_beat() -> None:
    """attach_engine must set engine.on_beat to _inject_beat."""
    inject_proc = CountingInjectProcessor()

    async def noop(event: BeatEvent) -> None:
        pass

    engine = CountingEngine(ExerciseMode.metronome, 0.1, on_beat=noop)
    inject_proc.attach_engine(engine)

    assert engine.on_beat == inject_proc._inject_beat


async def test_full_engine_cues_reach_inject() -> None:
    """Engine beats must drive inject_proc._inject_beat producing TextFrames."""
    inject_proc = CountingInjectProcessor()
    received_texts: list[str] = []

    async def mock_push(frame, direction=None) -> None:
        if isinstance(frame, TextFrame):
            received_texts.append(frame.text)

    inject_proc.push_frame = mock_push

    async def noop(event: BeatEvent) -> None:
        pass

    engine = CountingEngine(
        mode=ExerciseMode.metronome,
        interval_sec=0.05,
        on_beat=noop,
        exercise_name="푸시업",
        cue_mode="random",
    )
    inject_proc.attach_engine(engine)

    await engine.start()
    await asyncio.sleep(0.35)
    await engine.stop()

    assert len(received_texts) >= 2
    assert all(t != "" for t in received_texts)


async def test_process_frame_passes_through() -> None:
    """process_frame must forward all non-beat frames unchanged."""
    from pipecat.frames.frames import TextFrame
    from pipecat.tests.utils import run_test

    inject_proc = CountingInjectProcessor()
    frame = TextFrame(text="hello")
    downstream, _ = await run_test(inject_proc, frames_to_send=[frame])

    texts = [f.text for f in downstream if isinstance(f, TextFrame)]
    assert "hello" in texts
