"""Fixed #5 allocation and selection; no ORM, UI, narrative prompts or new vendor.

The caller must provide an atomic durable AllocationStore before production use.
#20 owns binding that store and the authoritative clock to the private draft.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
import threading
from typing import Protocol

from signal_loop.contracts.validation import enum, fields, identifier, monday, require, string


CATALOG = {
    "F1": "What change would most help delivery in {project_name} next week?",
    "F2": "What change would make the workload in {project_name} more manageable?",
}


@dataclass(frozen=True)
class Slot:
    project: str
    week: str
    question: str
    project_name: str = field(repr=False)
    delivery: str
    workload: str


class Outcome(StrEnum):
    SHOWN = "shown"
    NO_QUESTION = "no_question"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class Decision:
    outcome: Outcome
    question: str | None = None
    text: str | None = field(default=None, repr=False)


class AllocationStore(Protocol):
    def reserve_once(self, slots: tuple[Slot, ...]) -> tuple[Slot, ...]:
        """Atomically commit the first allocation (including empty); never replace it."""

    def claim(self, slot: Slot) -> bool:
        """Commit one permanent claim for an exact reserved slot before AI. Never reset."""

    def record(self, slot: Slot, decision: Decision) -> None:
        """Commit a result to the private draft before returning it to the UI owner."""


class FakeAllocationStore:
    """Thread-safe synthetic contract fixture. Not durable; never a UI default."""
    def __init__(self):
        self._lock = threading.Lock()
        self._slots = None
        self._claimed = set()
        self.outcomes = {}

    def reserve_once(self, slots):
        with self._lock:
            if self._slots is None:
                self._slots = slots
            return self._slots

    def claim(self, slot):
        with self._lock:
            if self._slots is None or slot not in self._slots or slot in self._claimed:
                return False
            self._claimed.add(slot)
            return True

    def record(self, slot, decision):
        with self._lock:
            if slot not in self._claimed:
                raise ValueError("invalid_allocation")
            self.outcomes.setdefault(slot, decision)


def _now():
    return datetime.now(timezone.utc)


def _remaining(deadline, clock):
    at = clock()
    require(isinstance(deadline, datetime) and deadline.utcoffset() is not None)
    require(isinstance(at, datetime) and at.utcoffset() is not None)
    return (deadline - at).total_seconds()


def reserve_followups(projects, *, remaining_budget, deadline, store: AllocationStore, clock=_now):
    """Freeze all candidates before any call, in priority then supplied frozen order.

Input is 0-3 selected project objects with project/week/project_name/answers.
Only J1/J2 enums affect selection. J3 may be present as bounded feedback data but
is never forwarded. Invalid, expired or exhausted input returns an empty tuple.
"""
    try:
        require(type(remaining_budget) is int and 0 <= remaining_budget <= 2)
        if remaining_budget == 0 or _remaining(deadline, clock) <= 0:
            return ()
        require(type(projects) in (list, tuple) and len(projects) <= 3)
        candidates = []
        seen = set()
        for order, project in enumerate(projects):
            fields(project, {"project", "week", "project_name", "answers"})
            identifier(project["project"])
            monday(project["week"])
            string(project["project_name"], 200)
            require(project["project"] not in seen)
            seen.add(project["project"])
            answers = project["answers"]
            fields(answers, {"J1", "J2"}, {"J3"})
            enum(answers["J1"], {"on_track", "at_risk", "blocked", "not_enough_context", "prefer_not_to_say"})
            enum(answers["J2"], {"manageable", "stretched", "overloaded", "not_enough_context", "prefer_not_to_say"})
            if "J3" in answers:
                string(answers["J3"], 320, 0)
            priorities = []
            if answers["J1"] in {"blocked", "at_risk"}:
                priorities.append((1 if answers["J1"] == "blocked" else 3, "F1"))
            if answers["J2"] in {"overloaded", "stretched"}:
                priorities.append((2 if answers["J2"] == "overloaded" else 4, "F2"))
            if priorities:
                priority, question = min(priorities)
                candidates.append((priority, order, Slot(project["project"], project["week"], question,
                                                        project["project_name"], answers["J1"], answers["J2"])))
        chosen = tuple(item[2] for item in sorted(candidates)[:remaining_budget])
        return store.reserve_once(chosen)
    except Exception:
        return ()


def select_followup(slot, *, store: AllocationStore, adapter, deadline, clock=_now):
    """Return one catalog question or safe continuation. Every claim is permanent."""
    try:
        remaining = _remaining(deadline, clock)
        # The store must recognize the exact frozen slot, including the enums.
        if not isinstance(slot, Slot) or not store.claim(slot):
            return Decision(Outcome.NO_QUESTION)
        remaining = min(remaining, _remaining(deadline, clock))
        if remaining <= 0:
            decision = Decision(Outcome.NO_QUESTION)
        else:
            request = {"schema": "followup-request/1.0", "project": slot.project, "week": slot.week,
                       "privacy_policy": "1.0", "question": slot.question,
                       "data": {"delivery": slot.delivery, "workload": slot.workload}}
            result = adapter.follow_up(request, time_allowance=min(2.0, remaining))
            if _remaining(deadline, clock) <= 0:
                decision = Decision(Outcome.NO_QUESTION)
            elif result.failure is not None or result.candidate is None:
                decision = Decision(Outcome.UNAVAILABLE)
            elif result.candidate["decision"] == "suppress":
                decision = Decision(Outcome.NO_QUESTION)
            else:
                decision = Decision(Outcome.SHOWN, slot.question,
                                    CATALOG[slot.question].format(project_name=slot.project_name))
        store.record(slot, decision)
        return decision
    except Exception:
        # A failed claim/save/provider must never expose text or replenish a slot.
        return Decision(Outcome.UNAVAILABLE)
