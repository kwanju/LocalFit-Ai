"""S2S/C2S round-trip — TextFrame in → real TTSAudioRawFrame out.

GPU-required because the pipeline includes the real Qwen3 TTS service loaded
from config.tts.active.  Skips cleanly when the adapter cannot load.
"""

import pytest
from pipecat.frames.frames import TextFrame, TTSAudioRawFrame
from pipecat.tests.utils import run_test

from app.adapters.tts import get_tts_adapter
from app.adapters.tts.qwen3_client import Qwen3TTSClient
from app.config import load_config
from app.pipecat_services.qwen3_tts_service import Qwen3TTSService

pytestmark = pytest.mark.gpu


@pytest.fixture(scope="module")
def tts_service():
    try:
        config = load_config()
    except FileNotFoundError:
        pytest.skip("config.yaml not found")

    try:
        client = get_tts_adapter(config)
    except Exception as e:
        pytest.skip(f"TTS adapter unavailable: {e}")

    if isinstance(client, Qwen3TTSClient):
        return Qwen3TTSService(client)
    pytest.skip(f"Unsupported active adapter: {type(client).__name__}")


@pytest.mark.asyncio
async def test_text_frame_produces_real_audio_frame(tts_service):
    """TextFrame('안녕하세요, 운동 시작할까요?') → ≥1 TTSAudioRawFrame with real PCM."""
    down, _ = await run_test(
        tts_service,
        frames_to_send=[TextFrame(text="안녕하세요, 운동 시작할까요?")],
    )
    audio_frames = [f for f in down if isinstance(f, TTSAudioRawFrame)]
    assert audio_frames, "expected at least one TTSAudioRawFrame"
    f0 = audio_frames[0]
    assert f0.sample_rate == 24000, f"unexpected sample_rate {f0.sample_rate}"
    assert f0.num_channels == 1
    assert len(f0.audio) > 1000, "frame audio is suspiciously short"
