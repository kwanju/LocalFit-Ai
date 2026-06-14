from pathlib import Path

from loguru import logger
from pydantic import BaseModel

DEFAULT_USER_ID: int = 1


class LLMConfig(BaseModel):
    host: str
    model: str          # 단일 모델 (ADR-029: qwen3.5:9b)
    timeout_sec: float
    keep_alive: str
    # qwen3.5:9b 는 thinking 모델 — structured 출력에선 reasoning 이 컨텍스트를 다
    # 채워 JSON 을 못 내므로 끈다(think=False). num_ctx/num_predict 는 Ollama native
    # /api/chat 옵션이며 /v1(OpenAI-compat)은 이를 무시한다. ADR-029 §thinking 참조.
    num_ctx: int = 8192
    num_predict: int = 512
    temperature: float = 0.7
    think: bool = False


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
    active: str = "qwen3"             # faster-qwen3-tts 단독 (ADR-006, MeloTTS 제거 2026-06-08)
    qwen3: dict[str, str]


class VADConfig(BaseModel):
    model: str
    threshold: float                  # ADR-007: silero confidence threshold (0..1)
    min_silence_ms: int               # 발화 종료 판정 최소 침묵 구간(ms) → Pipecat stop_secs
    sample_rate: int = 16000          # silero VAD 8k/16k만 지원, 우리는 16k 고정
    use_smart_turn: bool = False      # ADR-007: P1 검증 후 활성


class DBConfig(BaseModel):
    path: str


class EncouragementConfig(BaseModel):
    enabled: bool = True
    points: list[float] = [0.33, 0.66, 0.95]


class CountingConfig(BaseModel):
    beat_interval_sec: float
    max_reps: int
    start_delay_sec: float = 1.0          # ADR-014: LLM 응답 TTS 완료 후 grace
    plank_default_sec: int = 30
    rest_default_sec: int = 60
    auto_next_set: bool = False
    cue_selection: str = "random"         # "random" | "sequential"
    encouragement: EncouragementConfig = EncouragementConfig()


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
    calendar_pattern_weeks: int = 4          # ADR-013 §config: 캘린더 패턴 분석 기간
    response_length: CoachResponseLengthConfig = CoachResponseLengthConfig()
    instructor: InstructorConfig = InstructorConfig()


class NotificationsConfig(BaseModel):
    """능동 알림 + 백그라운드 스케줄러 기본값 (ADR-027).

    사용자 편집 가능한 값(enabled·lead·시각·음소거)은 DB ``notification_settings``
    단일 행이 source of truth 이고, 여기 값은 그 행을 처음 만들 때의 **시드 기본값**이다.
    ``poll_interval_sec`` · ``catchup_minutes`` 는 운영 노브라 config 전용(미편집).
    """

    enabled: bool = True
    lead_minutes: int = 10            # 운동 시간 N분 전 알림
    workout_time: str = "18:00"       # profile.available_times 미설정 시 기본 운동 리마인드 시각
    mute_start: str | None = "22:00"  # 음소거 시작 (None 이면 음소거 없음)
    mute_end: str | None = "07:00"    # 음소거 끝 (start>end 면 야간 래핑)
    checkin_enabled: bool = True
    checkin_time: str = "09:00"
    poll_interval_sec: int = 60       # 스케줄러(웹뷰 JS) 폴링 간격 — config 전용
    catchup_minutes: int = 30         # 놓친 알림 따라잡기 창 — config 전용


class GoogleCalendarConfig(BaseModel):
    """Google Calendar 연동 (ADR-022). 로컬-only(ADR-002)의 캘린더 한정 완화 — 본인
    계정 1개. 토큰은 평문 파일이 아니라 OS 자격증명 저장소(keyring)에 둔다(ADR-022 부정
    항목). 미연동/오프라인이면 모든 캘린더 기능은 graceful degrade 하고 로컬 스케줄·
    코칭은 계속된다(ADR-022 안 행복한 경로).

    ``credentials_path`` = 사용자가 Google Cloud Console 에서 발급한 OAuth Desktop
    client secret JSON 경로. 없으면 연동 자체가 비활성(연결 시도 시 안내).
    """

    enabled: bool = True
    credentials_path: str = "google_client_secret.json"  # OAuth Desktop client (사용자 발급)
    calendar_id: str = "primary"        # 단일 사용자 본인 기본 캘린더(ADR-002)
    event_duration_min: int = 30        # 등록할 운동 이벤트 기본 길이(분)
    workout_summary: str = "운동 (LocalFit)"  # 등록 이벤트 제목 — 읽기 필터 마커 겸용
    gap_day_end: str = "22:00"          # 틈새 추천 계산의 하루 끝(이후는 비는 시간 안 봄)
    gap_min_minutes: int = 30           # 이 분 이상 비어야 "틈새"로 추천


class AppConfig(BaseModel):
    llm: LLMConfig
    stt: STTConfig
    tts: TTSConfig
    vad: VADConfig
    db: DBConfig
    counting: CountingConfig
    coach: CoachConfig = CoachConfig()
    notifications: NotificationsConfig = NotificationsConfig()
    google_calendar: GoogleCalendarConfig = GoogleCalendarConfig()


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
