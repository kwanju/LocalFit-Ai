"""Session lifecycle state machine.

Pure Python — no FastAPI / SQLModel / Ollama imports (per CLAUDE.md §4).
The orchestrator drives transitions; this module only defines the legal set.
"""

import logging
from enum import Enum

logger = logging.getLogger(__name__)


class SessionState(str, Enum):
    IDLE = "idle"
    CONDITION_CHECK = "condition_check"
    WARMUP = "warmup"
    EXERCISING = "exercising"
    REST = "rest"
    COOLDOWN = "cooldown"
    COMPLETED = "completed"
    PAUSED = "paused"
    ABORTED = "aborted"
    INJURY_ALERT = "injury_alert"
    SAFETY_CHECK = "safety_check"
    EMERGENCY_STOPPED = "emergency_stopped"
    RECOVERED = "recovered"


_TERMINAL: frozenset[SessionState] = frozenset(
    {SessionState.COMPLETED, SessionState.ABORTED}
)

# Safety/injury transitions are allowed from any non-terminal state
# (INJURY_ALERT 인터셉터 — 모든 입력 가로채기, phase-4a doc).
_INTERCEPTOR_TARGETS: frozenset[SessionState] = frozenset(
    {SessionState.INJURY_ALERT, SessionState.SAFETY_CHECK, SessionState.EMERGENCY_STOPPED}
)

# Dict-based transition table. Explicit allow-list; anything not listed is illegal.
_TRANSITIONS: dict[SessionState, frozenset[SessionState]] = {
    SessionState.IDLE: frozenset({
        SessionState.CONDITION_CHECK,
        SessionState.EXERCISING,
        SessionState.ABORTED,
    }),
    SessionState.CONDITION_CHECK: frozenset({
        SessionState.WARMUP,
        SessionState.EXERCISING,
        SessionState.ABORTED,
    }),
    SessionState.WARMUP: frozenset({
        SessionState.EXERCISING,
        SessionState.PAUSED,
        SessionState.ABORTED,
    }),
    SessionState.EXERCISING: frozenset({
        SessionState.REST,
        SessionState.COOLDOWN,
        SessionState.PAUSED,
        SessionState.ABORTED,
    }),
    SessionState.REST: frozenset({
        SessionState.EXERCISING,
        SessionState.COOLDOWN,
        SessionState.PAUSED,
        SessionState.ABORTED,
    }),
    SessionState.COOLDOWN: frozenset({
        SessionState.COMPLETED,
        SessionState.PAUSED,
        SessionState.ABORTED,
    }),
    SessionState.PAUSED: frozenset({
        SessionState.EXERCISING,
        SessionState.REST,
        SessionState.COOLDOWN,
        SessionState.ABORTED,
    }),
    SessionState.INJURY_ALERT: frozenset({
        SessionState.SAFETY_CHECK,
        SessionState.ABORTED,
    }),
    SessionState.SAFETY_CHECK: frozenset({
        SessionState.RECOVERED,
        SessionState.EMERGENCY_STOPPED,
        SessionState.ABORTED,
    }),
    SessionState.RECOVERED: frozenset({
        SessionState.EXERCISING,
        SessionState.REST,
        SessionState.ABORTED,
    }),
    SessionState.EMERGENCY_STOPPED: frozenset({SessionState.ABORTED}),
    SessionState.COMPLETED: frozenset(),
    SessionState.ABORTED: frozenset(),
}


class InvalidTransitionError(RuntimeError):
    """Raised when a state transition is not permitted."""

    def __init__(self, from_state: SessionState, to_state: SessionState) -> None:
        super().__init__(f"Invalid transition: {from_state.value} -> {to_state.value}")
        self.from_state = from_state
        self.to_state = to_state


def is_terminal(state: SessionState) -> bool:
    return state in _TERMINAL


def can_transition(from_state: SessionState, to_state: SessionState) -> bool:
    if from_state in _TERMINAL:
        return False
    if to_state in _INTERCEPTOR_TARGETS:
        return True
    return to_state in _TRANSITIONS.get(from_state, frozenset())


def transition(from_state: SessionState, to_state: SessionState) -> SessionState:
    """Return ``to_state`` if the transition is legal, else raise ``InvalidTransitionError``."""
    if not can_transition(from_state, to_state):
        raise InvalidTransitionError(from_state, to_state)
    logger.info("Session state transition: %s -> %s", from_state.value, to_state.value)
    return to_state
