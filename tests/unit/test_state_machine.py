import pytest

from app.core.state_machine import (
    InvalidTransitionError,
    SessionState,
    can_transition,
    is_terminal,
    transition,
)


def test_legal_happy_path() -> None:
    chain = [
        SessionState.IDLE,
        SessionState.CONDITION_CHECK,
        SessionState.WARMUP,
        SessionState.EXERCISING,
        SessionState.REST,
        SessionState.EXERCISING,
        SessionState.COOLDOWN,
        SessionState.COMPLETED,
    ]
    state = chain[0]
    for nxt in chain[1:]:
        state = transition(state, nxt)
    assert state == SessionState.COMPLETED


def test_illegal_transition_raises() -> None:
    with pytest.raises(InvalidTransitionError):
        transition(SessionState.IDLE, SessionState.REST)


def test_terminal_states_block_all() -> None:
    assert is_terminal(SessionState.COMPLETED)
    assert is_terminal(SessionState.ABORTED)
    assert not can_transition(SessionState.COMPLETED, SessionState.EXERCISING)
    assert not can_transition(SessionState.ABORTED, SessionState.EXERCISING)


@pytest.mark.parametrize(
    "origin",
    [
        SessionState.IDLE,
        SessionState.WARMUP,
        SessionState.EXERCISING,
        SessionState.REST,
        SessionState.COOLDOWN,
    ],
)
def test_safety_intercepts_from_any_nonterminal(origin: SessionState) -> None:
    assert can_transition(origin, SessionState.INJURY_ALERT)
    assert can_transition(origin, SessionState.EMERGENCY_STOPPED)
    assert can_transition(origin, SessionState.SAFETY_CHECK)


def test_safety_does_not_intercept_terminal() -> None:
    assert not can_transition(SessionState.COMPLETED, SessionState.EMERGENCY_STOPPED)


def test_safety_check_recovery_path() -> None:
    state = transition(SessionState.INJURY_ALERT, SessionState.SAFETY_CHECK)
    state = transition(state, SessionState.RECOVERED)
    state = transition(state, SessionState.EXERCISING)
    assert state == SessionState.EXERCISING
