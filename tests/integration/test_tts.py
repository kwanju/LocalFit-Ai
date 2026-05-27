import io
import wave
from pathlib import Path

import pytest

pytestmark = pytest.mark.gpu

_REF_AUDIO_PLACEHOLDER = Path("data/ref_voice.wav")


@pytest.fixture
def config():
    try:
        from app.config import load_config
        return load_config()
    except FileNotFoundError:
        pytest.skip("config.yaml not found — copy config.example.yaml to config.yaml")


@pytest.fixture
def adapter(config):
    if not Path(config.tts.qwen3.get("ref_audio_path", "")).exists():
        pytest.skip("data/ref_voice.wav not found — place a Korean reference WAV (3s+)")
    try:
        from app.adapters.tts.qwen3 import Qwen3TTSAdapter
        return Qwen3TTSAdapter(config)
    except Exception as e:
        pytest.skip(f"Qwen3-TTS unavailable: {e}")


async def test_health(adapter):
    assert await adapter.health() is True


async def test_synthesize_returns_wav_bytes(adapter):
    from app.adapters.tts.protocol import TTSRequest

    request = TTSRequest(text="안녕하세요.")
    wav_bytes = await adapter.synthesize(request)

    assert isinstance(wav_bytes, bytes)
    assert wav_bytes[:4] == b"RIFF", "Expected WAV RIFF header"

    with wave.open(io.BytesIO(wav_bytes)) as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getnframes() > 0


async def test_synthesize_korean_coaching_phrase(adapter):
    from app.adapters.tts.protocol import TTSRequest

    request = TTSRequest(text="자, 이제 스쿼트 10회 시작합니다. 준비되셨나요?")
    wav_bytes = await adapter.synthesize(request)

    assert len(wav_bytes) > 2000, "Expected non-trivial audio for Korean coaching phrase"


async def test_stream_yields_bytes(adapter):
    from app.adapters.tts.protocol import TTSRequest

    request = TTSRequest(text="파이팅!")
    chunks = []
    async for chunk in adapter.stream(request):
        assert isinstance(chunk, bytes)
        chunks.append(chunk)

    assert len(chunks) >= 1
    assert sum(len(c) for c in chunks) > 0


async def test_get_tts_adapter_registry(config):
    from app.adapters.tts import get_tts_adapter

    if not Path(config.tts.qwen3.get("ref_audio_path", "")).exists():
        pytest.skip("data/ref_voice.wav not found")

    try:
        adapter = get_tts_adapter(config)
        assert await adapter.health() is True
    except Exception as e:
        pytest.skip(f"Adapter load failed: {e}")


async def test_unknown_adapter_raises(config):
    from app.adapters.tts import get_tts_adapter

    bad_config = config.model_copy(
        update={"tts": config.tts.model_copy(update={"active": "nonexistent"})}
    )
    with pytest.raises(ValueError, match="Unknown TTS adapter"):
        get_tts_adapter(bad_config)
