import io
import wave
from pathlib import Path

import pytest

np = pytest.importorskip("numpy", reason="numpy not installed — run: uv pip install -e '.[stt]'")

pytestmark = pytest.mark.gpu

_FIXTURE_AUDIO = Path(__file__).parent.parent / "fixtures" / "korean_sample.wav"


def _make_silent_wav(duration_ms: int = 500, sample_rate: int = 16000) -> bytes:
    n_samples = sample_rate * duration_ms // 1000
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(np.zeros(n_samples, dtype=np.int16).tobytes())
    return buf.getvalue()


@pytest.fixture
def config():
    try:
        from app.config import load_config
        return load_config()
    except FileNotFoundError:
        pytest.skip("config.yaml not found — copy config.example.yaml to config.yaml")


@pytest.fixture
def adapter(config):
    try:
        from app.adapters.stt.whisper import FasterWhisperAdapter
        return FasterWhisperAdapter(config)
    except Exception as e:
        pytest.skip(f"FasterWhisper model unavailable: {e}")


async def test_health(adapter):
    assert await adapter.health() is True


async def test_transcribe_returns_result_structure(adapter):
    from app.adapters.stt.protocol import STTResult

    result = await adapter.transcribe(_make_silent_wav(500))
    assert isinstance(result, STTResult)
    assert isinstance(result.text, str)
    assert isinstance(result.language, str)
    assert isinstance(result.duration_ms, int)
    assert result.duration_ms >= 0


_korean_fixture_exists = _FIXTURE_AUDIO.exists()


@pytest.mark.skipif(not _korean_fixture_exists, reason="tests/fixtures/korean_sample.wav not found")
async def test_transcribe_korean_sample(adapter):
    result = await adapter.transcribe(_FIXTURE_AUDIO.read_bytes())
    assert len(result.text) > 0, "Expected non-empty transcription for Korean audio"
    assert result.language == "ko"
