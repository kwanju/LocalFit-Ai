import logging
from pathlib import Path

import yaml
from pydantic import BaseModel

logger = logging.getLogger(__name__)

DEFAULT_USER_ID: int = 1


class LLMConfig(BaseModel):
    host: str
    active: str
    models: dict[str, str]
    timeout_sec: float
    keep_alive: str


class STTConfig(BaseModel):
    model: str
    device: str
    compute_type: str
    language: str


class TTSConfig(BaseModel):
    active: str
    kokoro: dict[str, str]
    qwen3: dict[str, str]


class VADConfig(BaseModel):
    model: str
    threshold: float
    min_silence_ms: int


class DBConfig(BaseModel):
    path: str


class CountingConfig(BaseModel):
    beat_interval_sec: float
    max_reps: int


class AppConfig(BaseModel):
    llm: LLMConfig
    stt: STTConfig
    tts: TTSConfig
    vad: VADConfig
    db: DBConfig
    counting: CountingConfig


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return AppConfig(**data)
    except FileNotFoundError:
        logger.error("Config file not found: %s — copy config.example.yaml to config.yaml", path)
        raise
    except Exception as e:
        logger.error("Failed to load config from %s: %s", path, e)
        raise
