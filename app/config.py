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
    beam_size: int = 1
    vad_filter: bool = True
    resample_to: int = 16000          # ADR-005: 입력 샘플레이트 != 16000이면 강제 리샘플


class TTSConfig(BaseModel):
    active: str                       # "qwen3" | "melo"  (ADR-006)
    qwen3: dict[str, str]
    melo: dict[str, str] = {}         # ADR-006 (2026-06-02 개정): MeloTTS 병행 어댑터


class VADConfig(BaseModel):
    model: str
    threshold: float                  # ADR-007: silero confidence threshold (0..1)
    min_silence_ms: int               # 발화 종료 판정 최소 침묵 구간(ms) → Pipecat stop_secs
    sample_rate: int = 16000          # silero VAD 8k/16k만 지원, 우리는 16k 고정
    use_smart_turn: bool = False      # ADR-007: P1 검증 후 활성


class DBConfig(BaseModel):
    path: str


class CountingConfig(BaseModel):
    beat_interval_sec: float
    max_reps: int


class InstructorConfig(BaseModel):
    max_retries: int = 2
    mode: str = "json"               # ADR-013: instructor.Mode.JSON for Ollama


class CoachResponseLengthConfig(BaseModel):
    """Soft length budgets — Pydantic ``max_length=500`` is the hard cap (ADR-013)."""

    proactive_opener_max: int = 70
    proactive_proposal_max: int = 120
    reactive_max: int = 500
    safety_max: int = 150


class CoachConfig(BaseModel):
    proactive_opener: bool = True
    context_recent_sessions: int = 5
    response_length: CoachResponseLengthConfig = CoachResponseLengthConfig()
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
