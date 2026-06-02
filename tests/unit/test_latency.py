"""LatencyTracker unit tests (ADR-018)."""

import pytest
from loguru import logger

from app.utils.latency import LatencyTracker


@pytest.fixture
def captured_logs():
    sink = []
    handler_id = logger.add(lambda msg: sink.append(msg), level="INFO")
    yield sink
    logger.remove(handler_id)


def test_context_manager_emits_metric(captured_logs):
    with LatencyTracker("test.stage"):
        pass
    joined = "".join(captured_logs)
    assert "latency.test.stage=" in joined
    assert "ms" in joined


def test_stop_emits_once(captured_logs):
    tracker = LatencyTracker("test.early")
    tracker.__enter__()
    tracker.stop()
    tracker.stop()  # second call must be a no-op
    tracker.__exit__(None, None, None)
    count = "".join(captured_logs).count("latency.test.early=")
    assert count == 1


def test_stop_returns_elapsed_ms():
    tracker = LatencyTracker("test.elapsed")
    tracker.__enter__()
    elapsed = tracker.stop()
    assert elapsed >= 0.0
    # second stop returns 0 (sentinel for "already emitted")
    assert tracker.stop() == 0.0
