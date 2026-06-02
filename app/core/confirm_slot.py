"""ConfirmSlot — tiny per-session memory holding the latest ``ProposeSetAction``
that the coach has offered. Shared between ``ConfirmRuleProcessor`` and
``ActionDispatcherProcessor`` (ADR-013 §확답 룰 / §액션 디스패처).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.coach_response import ProposeSetAction


@dataclass
class ConfirmSlot:
    pending_proposal: ProposeSetAction | None = None

    def set(self, action: ProposeSetAction) -> None:
        self.pending_proposal = action

    def take(self) -> ProposeSetAction | None:
        p = self.pending_proposal
        self.pending_proposal = None
        return p

    def clear(self) -> None:
        self.pending_proposal = None

    @property
    def has_pending(self) -> bool:
        return self.pending_proposal is not None
