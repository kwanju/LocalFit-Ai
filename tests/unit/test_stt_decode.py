import io
import wave

import pytest

np = pytest.importorskip("numpy", reason="numpy not installed — run: uv pip install -e '.[stt]'")

from app.adapters.stt.whisper import _decode_audio  # noqa: E402


def _make_wav(
    samples: np.ndarray,
    sample_rate: int = 16000,
    n_channels: int = 1,
    sampwidth: int = 2,
) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(n_channels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(sample_rate)
        wf.writeframes(samples.tobytes())
    return buf.getvalue()


def test_decode_mono_wav_returns_float32():
    pcm = np.zeros(1600, dtype=np.int16)
    result = _decode_audio(_make_wav(pcm))
    assert result.dtype == np.float32
    assert result.ndim == 1
    assert len(result) == 1600


def test_decode_mono_wav_normalizes_range():
    pcm = np.array([0, 32767, -32768], dtype=np.int16)
    result = _decode_audio(_make_wav(pcm))
    assert pytest.approx(result[0], abs=1e-5) == 0.0
    assert result[1] > 0.999
    assert result[2] < -0.999


def test_decode_stereo_wav_mixes_to_mono():
    left = np.full(800, 16384, dtype=np.int16)
    right = np.full(800, -16384, dtype=np.int16)
    interleaved = np.empty(1600, dtype=np.int16)
    interleaved[0::2] = left
    interleaved[1::2] = right
    result = _decode_audio(_make_wav(interleaved, n_channels=2))
    assert result.ndim == 1
    assert len(result) == 800
    assert np.allclose(result, 0.0, atol=1e-4)


def test_decode_unsupported_sample_width_raises():
    pcm = np.zeros(400, dtype=np.int16)
    wav_bytes = _make_wav(pcm, sampwidth=2)
    # Patch sampwidth in the WAV header to 3 (unsupported)
    header = bytearray(wav_bytes)
    # Byte 32-33: block align; byte 34-35: bits per sample → sampwidth is at offset 34
    # WAV fmt chunk: offset 34 = BitsPerSample, sampwidth = BitsPerSample // 8
    # Set BitsPerSample to 24 (3 bytes)
    header[34] = 24
    header[35] = 0
    # Also update block align (offset 32) = n_channels * sampwidth = 1 * 3 = 3
    header[32] = 3
    header[33] = 0
    with pytest.raises(ValueError, match="Unsupported PCM sample width"):
        _decode_audio(bytes(header))


def test_decode_raw_int16_pcm_without_header():
    raw = np.array([0, 16384, -16384], dtype=np.int16).tobytes()
    result = _decode_audio(raw)
    assert result.dtype == np.float32
    assert len(result) == 3
    assert pytest.approx(result[0], abs=1e-5) == 0.0
    assert result[1] > 0.49
    assert result[2] < -0.49
