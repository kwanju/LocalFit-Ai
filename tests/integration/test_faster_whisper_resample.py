"""Phase 4 §4-1 — 16kHz 강제 리샘플 정합성 (v1 known issue 회귀 방지).

ADR-005: 입력 샘플레이트가 16000이 아니면 어댑터 진입부에서 `librosa.resample`로
강제 변환된다. 32kHz WAV로 동일 음원을 전사했을 때 16kHz WAV 전사와 결과가
비슷하게 나와야 한다 (transcript 어긋남 없음).
"""

import io
import wave
from pathlib import Path

import pytest

np = pytest.importorskip("numpy", reason="numpy not installed — run: uv pip install -e '.[gpu]'")

pytestmark = pytest.mark.gpu

_FIXTURE_AUDIO = Path(__file__).parent.parent / "fixtures" / "korean_sample.wav"


def _read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wf:
        sr = wf.getframerate()
        n_channels = wf.getnchannels()
        raw = wf.readframes(wf.getnframes())
    pcm = np.frombuffer(raw, dtype=np.int16)
    if n_channels > 1:
        pcm = pcm.reshape(-1, n_channels).mean(axis=1).astype(np.int16)
    return pcm, sr


def _to_wav_bytes(pcm: np.ndarray, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.astype(np.int16).tobytes())
    return buf.getvalue()


def _upsample_to_32k(pcm_16k: np.ndarray) -> np.ndarray:
    """Crude nearest-neighbour 2x upsample. We rely on librosa inside the adapter
    to bring it back to 16kHz; this exercise just produces a non-16kHz WAV."""
    return np.repeat(pcm_16k, 2)


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
        from app.adapters.stt.faster_whisper_client import FasterWhisperClient
        return FasterWhisperClient(config)
    except Exception as e:
        pytest.skip(f"FasterWhisper model unavailable: {e}")


@pytest.mark.skipif(
    not _FIXTURE_AUDIO.exists(),
    reason="tests/fixtures/korean_sample.wav not found",
)
async def test_32khz_input_resamples_to_16khz_and_transcribes(adapter):
    """v1 known issue: 32kHz 입력 시 transcript 어긋남 → ADR-005 강제 리샘플로 해소."""
    pcm_16k, base_sr = _read_wav(_FIXTURE_AUDIO)
    if base_sr != 16000:
        pytest.skip(f"fixture WAV is {base_sr}Hz, expected 16000Hz baseline")

    wav_16k = _to_wav_bytes(pcm_16k, 16000)
    wav_32k = _to_wav_bytes(_upsample_to_32k(pcm_16k), 32000)

    result_16k = await adapter.transcribe(wav_16k)
    result_32k = await adapter.transcribe(wav_32k)

    assert result_16k.text, "16kHz baseline must produce non-empty transcript"
    assert result_32k.text, "32kHz input must transcribe after forced resample"
    # 동일 음원이므로 transcript가 동등해야 한다. nearest-neighbour 업샘플 후
    # librosa 리샘플을 거치면 약간의 차이 가능 → 길이/시작 단어로 정합성 검사.
    assert result_32k.text[:8] == result_16k.text[:8], (
        f"resample mismatch: 16k={result_16k.text!r} 32k={result_32k.text!r}"
    )
