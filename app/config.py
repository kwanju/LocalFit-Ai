from pathlib import Path

from loguru import logger
from pydantic import BaseModel

DEFAULT_USER_ID: int = 1


class LLMConfig(BaseModel):
    host: str
    model: str          # 단일 모델 (ADR-004: qwen3:8b)
    timeout_sec: float
    keep_alive: str


class STTConfig(BaseModel):
    model: str
    device: str
    compute_type: str
    language: str
    timeout_sec: float = 30.0


class TTSConfig(BaseModel):
    active: str                       # "qwen3" | "melo"  (ADR-006)
    qwen3: dict[str, str]
    melo: dict[str, str] = {}         # ADR-006 (2026-06-02 개정): MeloTTS 병행 어댑터


class VADConfig(BaseModel):
    model: str
    threshold: float
    min_silence_ms: int


class DBConfig(BaseModel):
    path: str


class CountingConfig(BaseModel):
    beat_interval_sec: float
    max_reps: int


class InstructorConfig(BaseModel):
    max_retries: int = 2


class CoachConfig(BaseModel):
    proactive_opener: bool = True
    instructor: InstructorConfig = InstructorConfig()


class AppConfig(BaseModel):
    llm: LLMConfig
    stt: STTConfig
    tts: TTSConfig
    vad: VADConfig
    db: DBConfig
    counting: CountingConfig
    coach: CoachConfig = CoachConfig()


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    import yaml

    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return AppConfig(**data)
    except FileNotFoundError:
        logger.error("Config file not found: {} — copy config.example.yaml to config.yaml", path)
        raise
    except Exception as e:
        logger.error("Failed to load config from {}: {}", path, e)
        raise
