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
    s2s = "s2s"
    c2s = "c2s"
    c2c = "c2c"
    s2c = "s2c"


class SessionStatus(StrEnum):
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"


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
    __tablename__ = "condition_log"

    id: int | None = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="session.id")
    logged_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    fatigue_level: int | None = None  # 1–10
    pain_report: str | None = None
    notes: str | None = None


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
