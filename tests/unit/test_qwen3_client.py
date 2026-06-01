"""Unit tests for Qwen3TTSClient — GPU-free.

Tests pure logic only: WAV encoding, TTSRequest dataclass, and config validation
paths that raise before any model load. GPU-requiring synthesis tests are in
tests/integration/test_tts.py (pytest.mark.gpu).
"""

import io
import struct
import wave

import numpy as np
import pytest

from app.adapters.tts.qwen3_client import TTSRequest, _float32_to_wav


class TestFloat32ToWav:
    def test_returns_valid_wav_header(self) -> None:
        audio = np.zeros(100, dtype=np.float32)
        wav_bytes = _float32_to_wav(audio, sample_rate=24000)
        assert wav_bytes[:4] == b"RIFF"
        assert wav_bytes[8:12] == b"WAVE"

    def test_mono_16bit(self) -> None:
        audio = np.zeros(240, dtype=np.float32)
        wav_bytes = _float32_to_wav(audio, sample_rate=24000)
        with wave.open(io.BytesIO(wav_bytes)) as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 24000
            assert wf.getnframes() == 240

    def test_clips_to_int16_range(self) -> None:
        audio = np.array([2.0, -2.0], dtype=np.float32)
        wav_bytes = _float32_to_wav(audio, sample_rate=24000)
        with wave.open(io.BytesIO(wav_bytes)) as wf:
            raw = wf.readframes(2)
        s0, s1 = struct.unpack_from("<hh", raw)
        assert s0 == 32767
        assert s1 == -32768

    def test_empty_audio(self) -> None:
        audio = np.array([], dtype=np.float32)
        wav_bytes = _float32_to_wav(audio, sample_rate=16000)
        with wave.open(io.BytesIO(wav_bytes)) as wf:
            assert wf.getnframes() == 0


class TestTTSRequest:
    def test_defaults(self) -> None:
        req = TTSRequest(text="안녕하세요")
        assert req.text == "안녕하세요"
        assert req.voice == "default"
        assert req.speed == 1.0

    def test_custom_speed(self) -> None:
        req = TTSRequest(text="test", speed=1.5)
        assert req.speed == 1.5


class TestQwen3TTSClientConfigValidation:
    """Tests that validate config errors *before* model loading (no GPU needed)."""

    def _make_config(self, overrides: dict):
        from unittest.mock import MagicMock

        cfg = MagicMock()
        defaults = {
            "model_id": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
            "ref_audio_path": "",
            "ref_text": "",
            "timeout_sec": "60.0",
            "attn_implementation": "sdpa",
            "device_map": "cuda:0",
        }
        defaults.update(overrides)
        cfg.tts.qwen3.get = lambda k, d="": defaults.get(k, d)
        cfg.tts.qwen3.__contains__ = lambda self, k: k in defaults
        cfg.tts.qwen3.__getitem__ = lambda self, k: defaults[k]
        return cfg

    def test_missing_ref_audio_path_raises(self) -> None:
        from app.adapters.tts.qwen3_client import Qwen3TTSClient

        cfg = self._make_config({"ref_audio_path": ""})
        with pytest.raises(ValueError, match="ref_audio_path"):
            Qwen3TTSClient(cfg)

    def test_nonexistent_ref_audio_raises(self, tmp_path) -> None:
        from app.adapters.tts.qwen3_client import Qwen3TTSClient

        cfg = self._make_config({"ref_audio_path": str(tmp_path / "no_such.wav")})
        with pytest.raises(FileNotFoundError, match="no_such.wav"):
            Qwen3TTSClient(cfg)

    def test_missing_model_id_raises(self, tmp_path) -> None:
        from unittest.mock import MagicMock

        from app.adapters.tts.qwen3_client import Qwen3TTSClient

        ref = tmp_path / "ref.wav"
        ref.write_bytes(b"dummy")

        cfg = MagicMock()
        cfg.tts.qwen3.get = lambda k, d="": {
            "ref_audio_path": str(ref),
            "ref_text": "",
            "timeout_sec": "60.0",
        }.get(k, d)
        cfg.tts.qwen3.__contains__ = lambda self, k: k != "model_id"
        with pytest.raises(ValueError, match="model_id"):
            Qwen3TTSClient(cfg)
