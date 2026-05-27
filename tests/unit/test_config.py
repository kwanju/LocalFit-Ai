import pytest
import yaml

from app.config import AppConfig, load_config


def test_load_config_success(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        yaml.dump({
            "llm": {
                "host": "http://127.0.0.1:11434",
                "active": "qwen3.5",
                "models": {"qwen3.5": "qwen3.5:9b"},
                "timeout_sec": 4.0,
                "keep_alive": "10m",
            },
            "stt": {
                "model": "large-v3-turbo",
                "device": "cuda",
                "compute_type": "float16",
                "language": "ko",
            },
            "tts": {
                "active": "kokoro",
                "kokoro": {"voice": "af_heart", "speed": "1.0"},
                "qwen3": {"voice": "default", "speed": "1.0"},
            },
            "vad": {
                "model": "silero_vad",
                "threshold": 0.5,
                "min_silence_ms": 700,
            },
            "db": {"path": "data/localfit.db"},
            "counting": {"beat_interval_sec": 2.0, "max_reps": 200},
        }),
        encoding="utf-8",
    )

    config = load_config(cfg_file)

    assert isinstance(config, AppConfig)
    assert config.llm.active == "qwen3.5"
    assert config.llm.models["qwen3.5"] == "qwen3.5:9b"
    assert config.stt.language == "ko"
    assert config.tts.active == "kokoro"
    assert config.counting.beat_interval_sec == 2.0


def test_load_config_file_not_found():
    with pytest.raises(FileNotFoundError):
        load_config("nonexistent.yaml")


def test_load_config_missing_required_field(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(yaml.dump({"llm": {"host": "http://127.0.0.1:11434"}}), encoding="utf-8")

    with pytest.raises(Exception):
        load_config(cfg_file)
