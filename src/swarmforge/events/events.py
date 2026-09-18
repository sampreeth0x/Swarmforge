"""Event model — the observability spine of the swarm."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class EventKind(StrEnum):
    MISSION_CREATED = "mission.created"
    PLAN_READY = "plan.ready"
    TASK_CLAIMED = "task.claimed"
    AGENT_STEP = "agent.step"
    TOOL_CALLED = "tool.called"
    TOOL_RESULT = "tool.result"
    SANDBOX_CREATED = "sandbox.created"
    SANDBOX_FORKED = "sandbox.forked"
    TESTS_PASSED = "tests.passed"
    TESTS_FAILED = "tests.failed"
    CANDIDATE_READY = "candidate.ready"
    VERDICT = "verdict"
    MERGE_CONFLICT = "merge.conflict"
    MERGE_DONE = "merge.done"
    MISSION_DONE = "mission.done"
    MISSION_FAILED = "mission.failed"
    USAGE = "usage"


@dataclass(frozen=True, slots=True)
class Event:
    kind: EventKind
    mission_id: str
    payload: dict = field(default_factory=dict)
    agent_id: str | None = None
    id: int = 0  # assigned by the store on persist
    ts: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_sse_dict(self) -> dict:
        return {
            "id": self.id,
            "ts": self.ts.isoformat(),
            "kind": str(self.kind),
            "mission_id": self.mission_id,
            "agent_id": self.agent_id,
            "payload": self.payload,
        }
