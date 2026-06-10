from datetime import UTC, datetime
from enum import StrEnum

from sqlmodel import Field, SQLModel

from app.config import DEFAULT_USER_ID

DEFAULT_REST_SEC: int = 60


class FitnessLevel(StrEnum):
    beginner = "beginner"
    intermediate = "intermediate"
    advanced = "advanced"


class CountingMode(StrEnum):
    metronome = "metronome"
    timer = "timer"


class SessionMode(StrEnum):
    # v4 (ADR-021): S2C(음성입력→텍스트출력) 제거 → 3모드. 기존 s2c 행은
    # app/db/migrations.py 가 s2s 로 변환.
    s2s = "s2s"
    c2s = "c2s"
    c2c = "c2c"


class SessionStatus(StrEnum):
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"


class MemoryKind(StrEnum):
    # 1층 구조화 메모리 종류 (ADR-025). injury=부상, constraint=금기·제약.
    injury = "injury"
    constraint = "constraint"


class UserProfile(SQLModel, table=True):
    __tablename__ = "user_profile"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(default="사용자")
    age: int | None = None
    weight_kg: float | None = None
    height_cm: float | None = None
    fitness_level: FitnessLevel = Field(default=FitnessLevel.beginner)
    goal: str | None = None  # 온보딩 1단계 목표 (PRD 부록 A-1)
    available_times: str = Field(default="[]")  # JSON array
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Exercise(SQLModel, table=True):
    __tablename__ = "exercise"

    id: int | None = Field(default=None, primary_key=True)
    name: str
    muscle_group: str
    equipment: str | None = None
    counting_mode: CountingMode = Field(default=CountingMode.metronome)
    description: str | None = None
    extra_data: str = Field(default="{}")  # JSON — "metadata" is reserved by SQLAlchemy


class Routine(SQLModel, table=True):
    __tablename__ = "routine"

    id: int | None = Field(default=None, primary_key=True)
    name: str
    description: str | None = None
    user_profile_id: int = Field(default=DEFAULT_USER_ID, foreign_key="user_profile.id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RoutineExercise(SQLModel, table=True):
    __tablename__ = "routine_exercise"

    id: int | None = Field(default=None, primary_key=True)
    routine_id: int = Field(foreign_key="routine.id")
    exercise_id: int = Field(foreign_key="exercise.id")
    sets: int
    reps: int | None = None
    duration_sec: int | None = None
    rest_sec: int = DEFAULT_REST_SEC
    order_index: int


class WorkoutSession(SQLModel, table=True):
    """Workout session — named WorkoutSession to avoid shadowing sqlmodel.Session."""

    __tablename__ = "session"

    id: int | None = Field(default=None, primary_key=True)
    user_profile_id: int = Field(default=DEFAULT_USER_ID, foreign_key="user_profile.id")
    routine_id: int | None = Field(default=None, foreign_key="routine.id")
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    ended_at: datetime | None = None
    status: SessionStatus = Field(default=SessionStatus.in_progress)
    mode: SessionMode = Field(default=SessionMode.c2c)
    extra_data: str = Field(default="{}")  # JSON — "metadata" is reserved by SQLAlchemy


class SetLog(SQLModel, table=True):
    __tablename__ = "set_log"

    id: int | None = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="session.id")
    exercise_id: int = Field(foreign_key="exercise.id")
    set_number: int
    reps_completed: int | None = None
    weight_kg: float | None = None
    duration_sec: int | None = None
    completed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    extra_data: str = Field(default="{}")  # JSON — "metadata" is reserved by SQLAlchemy


class ConditionLog(SQLModel, table=True):
    """자가보고 컨디션 체크인 (ADR-023). 세션 시작 전(또는 일일) 체크인은 ``session_id``
    없이 저장되고, 세션 생성 시 ``ConditionRepository.link_latest_unlinked`` 가 연결한다.

    ``fatigue_level`` 은 기존(v3) 1–10 척도 유지(LLM ``log_condition``·캘린더 집계와 공유).
    ``soreness`` 는 ADR-023 의 근육통 1–5 척도(신규).
    """

    __tablename__ = "condition_log"

    id: int | None = Field(default=None, primary_key=True)
    # nullable — 세션 전 일일 체크인 허용(ADR-023). 세션 생성 시 연결됨.
    session_id: int | None = Field(default=None, foreign_key="session.id")
    logged_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    fatigue_level: int | None = None  # 1–10
    soreness: int | None = None  # 1–5 (ADR-023 근육통)
    pain_report: str | None = None
    notes: str | None = None


class UserMemory(SQLModel, table=True):
    """1층 구조화 메모리 — 부상·제약 (ADR-025). 안전 직결이라 매 세션 전량 주입된다.

    단일 사용자(ADR-002)라 ``user_id`` 분기 없음. ``active=False`` 는 해소된 제약
    (이력 보존). ``severity`` 는 LLM/규칙이 채울 수 있는 선택 메타.
    """

    __tablename__ = "user_memory"

    id: int | None = Field(default=None, primary_key=True)
    kind: MemoryKind
    text: str
    severity: str | None = None
    active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class FitnessBaseline(SQLModel, table=True):
    """1층 기준선 — 첫 체력검증(ADR-028) 결과. **스키마만 phase v4-2 가 마련하고
    실제 채움은 phase v4-5 가 담당**. 종목·지표별 한 행(upsert).

    metric: "reps"(횟수 종목) | "duration_sec"(플랭크 등 시간 종목).
    """

    __tablename__ = "fitness_baseline"

    id: int | None = Field(default=None, primary_key=True)
    exercise: str
    metric: str
    value: int
    note: str | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MemoryFact(SQLModel, table=True):
    """2층 자유텍스트 메모 — 부드러운 선호·맥락 (ADR-025). 검색은 최근순/키워드
    (벡터 X). 토큰 예산 내 최근 N건만 주입되며, 잘려도 안전에는 영향 없음."""

    __tablename__ = "memory_fact"

    id: int | None = Field(default=None, primary_key=True)
    text: str
    tags: str = Field(default="[]")  # JSON array
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class InteractionLog(SQLModel, table=True):
    __tablename__ = "interaction_log"

    id: int | None = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="session.id")
    role: str  # "user" | "assistant"
    content: str
    input_mode: str | None = None  # "voice" | "text"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# PRD §5 에 정의된 4종 기본 운동 시드 데이터
EXERCISE_SEED: list[dict] = [
    {
        "name": "풀업",
        "muscle_group": "등·이두",
        "counting_mode": CountingMode.metronome,
        "description": "상체 당기기 복합 운동",
    },
    {
        "name": "푸시업",
        "muscle_group": "가슴·삼두",
        "counting_mode": CountingMode.metronome,
        "description": "상체 밀기 복합 운동",
    },
    {
        "name": "스쿼트",
        "muscle_group": "하체",
        "counting_mode": CountingMode.metronome,
        "description": "하체 복합 운동",
    },
    {
        "name": "플랭크",
        "muscle_group": "코어",
        "counting_mode": CountingMode.timer,
        "description": "코어 안정화 운동",
    },
]
