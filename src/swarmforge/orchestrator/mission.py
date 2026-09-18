"""Plan parsing + DAG validation for planner output."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field


class PlanError(Exception):
    pass


@dataclass(slots=True)
class SubTask:
    id: str
    title: str
    instructions: str
    acceptance_criteria: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    files_touched: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Plan:
    subtasks: list[SubTask]


def extract_json(text: str) -> dict:
    """Pull the first JSON object out of an LLM reply (handles ``` fences)."""
    text = text.strip()
    if "```" in text:
        for chunk in text.split("```"):
            chunk = chunk.strip()
            if chunk.startswith("json"):
                chunk = chunk[4:]
            chunk = chunk.strip()
            if chunk.startswith("{"):
                text = chunk
                break
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise PlanError("no JSON object found in planner output")
    return json.loads(text[start:end + 1])


def parse_plan(text: str) -> Plan:
    try:
        data = extract_json(text)
        raw = data.get("plan")
        if not isinstance(raw, list) or not raw:
            raise PlanError("plan must be a non-empty array")
        subtasks = []
        for t in raw:
            st = SubTask(
                id=str(t.get("id", "")),
                title=str(t.get("title", "untitled")),
                instructions=str(t.get("instructions", "")),
                acceptance_criteria=[str(c) for c in t.get("acceptance_criteria", [])],
                depends_on=[str(d) for d in t.get("depends_on", [])],
                files_touched=[str(f) for f in t.get("files_touched", [])],
            )
            if not st.id:
                raise PlanError("subtask missing id")
            subtasks.append(st)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise PlanError(f"invalid plan JSON: {exc}") from exc
    validate_dag(subtasks)
    return Plan(subtasks=subtasks)


def validate_dag(subtasks: list[SubTask]) -> None:
    ids = [s.id for s in subtasks]
    if len(ids) != len(set(ids)):
        raise PlanError("duplicate task ids in plan")
    id_set = set(ids)
    for s in subtasks:
        unknown = set(s.depends_on) - id_set
        if unknown:
            raise PlanError(f"task {s.id} depends on unknown tasks: {sorted(unknown)}")
    # cycle detection via DFS
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {s.id: WHITE for s in subtasks}
    deps = {s.id: set(s.depends_on) for s in subtasks}

    def visit(node: str) -> None:
        color[node] = GRAY
        for d in deps[node]:
            if color[d] == GRAY:
                raise PlanError(f"dependency cycle involving {node}")
            if color[d] == WHITE:
                visit(d)
        color[node] = BLACK

    for s in subtasks:
        if color[s.id] == WHITE:
            visit(s.id)


PLAN_JSON_HINT = re.compile(r"\{.*\}", re.DOTALL)  # reserved for stricter extraction later
