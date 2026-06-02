"""Integration tests for the TTS adapters (Qwen3 + Melo).  GPU-required."""

import time
import wave
from pathlib import Path

import pytest

pytestmark = pytest.mark.gpu

_SHORT_PHRASE = "안녕하세요, 운동 시작할까요?"
_FIVE_SAMPLES = 5
_FIRST_CHUNK_BUDGET_MS = 500.0  # PRD §4-1 / ADR-006


@pytest.fixture(scope="module")
def config():
    try:
        from app.config import load_config

        return load_config()
    except FileNotFoundError:
        pytest.skip("config.yaml not found")


def _has_ref_audio(config) -> bool:
    return Path(config.tts.qwen3.get("ref_audio_path", "")).exists()


# ---------------------------------------------------------------------------
# Qwen3-TTS
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def qwen3_client(config):
    if not _has_ref_audio(config):
        pytest.skip("data/ref_voice.wav not found — voice clone reference required")
    try:
        from app.adapters.tts.qwen3_client import Qwen3TTSClient

        return Qwen3TTSClient(config)
    except Exception as e:
        pytest.skip(f"Qwen3-TTS unavailable: {e}")


async def test_qwen3_health(qwen3_client):
    assert await qwen3_client.health() is True


async def test_qwen3_synthesize_returns_wav_bytes(qwen3_client):
    from app.adapters.tts.qwen3_client import TTSRequest

    wav = await qwen3_client.synthesize(TTSRequest(text="안녕하세요."))
    assert wav[:4] == b"RIFF"
    import io
    with wave.open(io.BytesIO(wav)) as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getnframes() > 0


async def test_qwen3_stream_yields_pcm_chunks(qwen3_client):
    chunks = []
    async for chunk in qwen3_client.stream(_SHORT_PHRASE):
        assert isinstance(chunk, bytes) and len(chunk) > 0
        chunks.append(chunk)
    assert len(chunks) >= 1


@pytest.mark.xfail(
    reason="Qwen3-TTS sentence-batch ≈ 5000ms (per-call fixed cost). ADR-006 2026-06-02 개정에서 "
    "Qwen3는 voice-clone 보조 옵션으로 강등 — 기본 tts.active='melo'. "
    "Qwen3 측정 기록 유지를 위해 xfail로 남김.",
    strict=False,
)
async def test_qwen3_first_chunk_5x_under_500ms(qwen3_client):
    """ADR-006 Phase 3 DoD — first-chunk latency 5x mean < 500ms.  Qwen3는 sentence-batch
    구조상 미달성 (실측 ~5000ms). 본 테스트는 회귀 추적용으로 xfail 유지."""
    samples: list[float] = []
    for _ in range(_FIVE_SAMPLES):
        t0 = time.monotonic()
        async for _chunk in qwen3_client.stream(_SHORT_PHRASE):
            samples.append((time.monotonic() - t0) * 1000.0)
            break
    mean_ms = sum(samples) / len(samples)
    print(f"\nQwen3-TTS first-chunk 5x samples (ms): {samples}")
    print(f"Qwen3-TTS first-chunk 5x mean: {mean_ms:.1f}ms (budget {_FIRST_CHUNK_BUDGET_MS}ms)")
    assert mean_ms < _FIRST_CHUNK_BUDGET_MS


# ---------------------------------------------------------------------------
# MeloTTS
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def melo_client(config):
    try:
        from app.adapters.tts.melo_client import MeloTTSClient

        return MeloTTSClient(config)
    except Exception as e:
        pytest.skip(f"MeloTTS unavailable: {e}")


async def test_melo_health(melo_client):
    assert await melo_client.health() is True


async def test_melo_synthesize_returns_wav_bytes(melo_client):
    wav = await melo_client.synthesize("안녕하세요.")
    assert wav[:4] == b"RIFF"


async def test_melo_stream_yields_pcm_chunks(melo_client):
    chunks = []
    async for chunk in melo_client.stream(_SHORT_PHRASE):
        assert isinstance(chunk, bytes) and len(chunk) > 0
        chunks.append(chunk)
    assert len(chunks) >= 1


async def test_melo_first_chunk_5x_under_500ms(melo_client):
    samples: list[float] = []
    for _ in range(_FIVE_SAMPLES):
        t0 = time.monotonic()
        async for _chunk in melo_client.stream(_SHORT_PHRASE):
            samples.append((time.monotonic() - t0) * 1000.0)
            break
    mean_ms = sum(samples) / len(samples)
    print(f"\nMeloTTS first-chunk 5x samples (ms): {samples}")
    print(f"MeloTTS first-chunk 5x mean: {mean_ms:.1f}ms (budget {_FIRST_CHUNK_BUDGET_MS}ms)")
    assert mean_ms < _FIRST_CHUNK_BUDGET_MS


# ---------------------------------------------------------------------------
# Adapter registry
# ---------------------------------------------------------------------------


async def test_unknown_adapter_raises(config):
    from app.adapters.tts import get_tts_adapter

    bad = config.model_copy(
        update={"tts": config.tts.model_copy(update={"active": "nonexistent"})}
    )
    with pytest.raises(ValueError, match="Unknown TTS adapter"):
        get_tts_adapter(bad)
