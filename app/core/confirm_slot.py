"""ConfirmSlot — tiny per-session memory holding the latest pending proposal
the coach has offered. Shared between ``ConfirmRuleProcessor`` and
``ActionDispatcherProcessor`` (ADR-013 §확답 룰 / §액션 디스패처).

Two independent kinds of pending proposal (ADR-024):
  * ``pending_proposal`` — a ``ProposeSetAction`` (accept → start counting).
  * ``pending_plan`` — a plan proposal/adjustment (accept → commit to DB).

A new proposal of one kind clears the other, so only one is ever pending at a
time — the user's "좋아요" is never ambiguous about which gate it confirms.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.coach_response import (
    ProposePlanAction,
    ProposePlanAdjustmentAction,
    ProposeSetAction,
)

PlanProposal = ProposePlanAction | ProposePlanAdjustmentAction


@dataclass
class ConfirmSlot:
    pending_proposal: ProposeSetAction | None = None
    pending_plan: PlanProposal | None = None

    def set(self, action: ProposeSetAction) -> None:
        self.pending_proposal = action
        self.pending_plan = None

    def take(self) -> ProposeSetAction | None:
        p = self.pending_proposal
        self.pending_proposal = None
        return p

    def set_plan(self, action: PlanProposal) -> None:
        self.pending_plan = action
        self.pending_proposal = None

    def take_plan(self) -> PlanProposal | None:
        p = self.pending_plan
        self.pending_plan = None
        return p

    def clear(self) -> None:
        self.pending_proposal = None
        self.pending_plan = None

    @property
    def has_pending(self) -> bool:
        return self.pending_proposal is not None

    @property
    def has_pending_plan(self) -> bool:
        return self.pending_plan is not None
