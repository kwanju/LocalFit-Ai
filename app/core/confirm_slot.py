"""ConfirmSlot — tiny per-session memory holding the latest pending proposal
the coach has offered. Shared between ``ConfirmRuleProcessor`` and
``ActionDispatcherProcessor`` (ADR-013 §확답 룰 / §액션 디스패처).

Three independent kinds of pending proposal:
  * ``pending_proposal`` — a ``ProposeSetAction`` (accept → start counting, ADR-024).
  * ``pending_plan`` — a plan proposal/adjustment (accept → commit to DB, ADR-024).
  * ``pending_calendar`` — a calendar-sync proposal (accept → register the active
    plan's events to Google Calendar, ADR-022 §9-2).

A new proposal of any kind clears the others, so only one is ever pending at a
time — the user's "좋아요" is never ambiguous about which gate it confirms.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.coach_response import (
    ProposeCalendarSyncAction,
    ProposePlanAction,
    ProposePlanAdjustmentAction,
    ProposeSetAction,
)

PlanProposal = ProposePlanAction | ProposePlanAdjustmentAction


@dataclass
class ConfirmSlot:
    pending_proposal: ProposeSetAction | None = None
    pending_plan: PlanProposal | None = None
    pending_calendar: ProposeCalendarSyncAction | None = None

    def set(self, action: ProposeSetAction) -> None:
        self.pending_proposal = action
        self.pending_plan = None
        self.pending_calendar = None

    def take(self) -> ProposeSetAction | None:
        p = self.pending_proposal
        self.pending_proposal = None
        return p

    def set_plan(self, action: PlanProposal) -> None:
        self.pending_plan = action
        self.pending_proposal = None
        self.pending_calendar = None

    def take_plan(self) -> PlanProposal | None:
        p = self.pending_plan
        self.pending_plan = None
        return p

    def set_calendar(self, action: ProposeCalendarSyncAction) -> None:
        self.pending_calendar = action
        self.pending_proposal = None
        self.pending_plan = None

    def take_calendar(self) -> ProposeCalendarSyncAction | None:
        p = self.pending_calendar
        self.pending_calendar = None
        return p

    def clear(self) -> None:
        self.pending_proposal = None
        self.pending_plan = None
        self.pending_calendar = None

    @property
    def has_pending(self) -> bool:
        return self.pending_proposal is not None

    @property
    def has_pending_plan(self) -> bool:
        return self.pending_plan is not None

    @property
    def has_pending_calendar(self) -> bool:
        return self.pending_calendar is not None
