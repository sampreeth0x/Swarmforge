"""Mission + task state machines — pure, unit-testable."""

from __future__ import annotations

from enum import StrEnum

MISSION_STATES = ("planning", "spawning", "executing", "verifying", "judging", "merging", "done", "failed")

MISSION_TRANSITIONS: dict[str, set[str]] = {
    "planning": {"spawning", "failed"},
    "spawning": {"executing", "failed"},
    "executing": {"verifying", "failed"},
    "verifying": {"judging", "failed"},
    "judging": {"merging", "failed"},
    "merging": {"done", "failed", "judging"},  # re-judge after dropped candidates
    "done": set(),
    "failed": set(),
}


def can_transition(current: str, nxt: str) -> bool:
    return nxt in MISSION_TRANSITIONS.get(current, set())


class TaskStatus(StrEnum):
    PENDING = "pending"    # deps not ready yet
    READY = "ready"        # deps done — claimable
    CLAIMED = "claimed"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    RETRYING = "retrying"


def mark_dependents_ready(tasks: list[dict]) -> list[str]:
    """Pure helper: returns ids of tasks whose deps are all done and that are still pending."""
    statuses = {t["id"]: t["status"] for t in tasks}
    out = []
    for t in tasks:
        if t["status"] != TaskStatus.PENDING:
            continue
        if all(statuses.get(d) == TaskStatus.DONE for d in t["depends_on"]):
            out.append(t["id"])
    return out
