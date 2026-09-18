"""Scripted mock provider — deterministic agent behavior with ZERO API keys.

Scenarios live in mock/scenarios/*.yaml:

    match:
      role: worker                    # optional
      prompt_contains: dark mode      # optional substring of the conversation
    steps:
      - tool_calls:
          - name: write_file
            arguments: {path: "static/dark.css", content: "..."}
      - final: "Done."

Steps are consumed in order across successive chat() calls; the first matching
scenario wins, and a catch-all (`match: {}`) keeps loops from dead-ending.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from swarmforge.llm.base import LLMResponse, Message, ToolCall, ToolSpec


class MockProvider:
    name = "mock"

    def __init__(self, scenario_dir: Path | str) -> None:
        self.scenario_dir = Path(scenario_dir)
        self._scenarios: list[dict[str, Any]] = []
        # Progress cursors are per (scenario file, session/agent) so parallel
        # workers replaying the same scenario advance independently.
        self._cursors: dict[tuple[str, str], int] = {}
        self._load_scenarios()

    def _load_scenarios(self) -> None:
        self._scenarios = []
        if not self.scenario_dir.is_dir():
            return
        for path in sorted(self.scenario_dir.glob("*.yaml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            data["_file"] = path.name
            self._scenarios.append(data)

    async def chat(self, messages: list[Message], *, tools: list[ToolSpec] | None = None,
                   model: str | None = None, temperature: float = 0.2,
                   max_tokens: int = 4096, role: str = "", session: str = "") -> LLMResponse:
        scenario = self._pick(role, messages)
        step = self._next_step(scenario, session)
        if step is None:
            return LLMResponse(message=Message(role="assistant", content="[mock: exhausted]"),
                               stop_reason="stop")
        if "tool_calls" in step:
            calls = [
                ToolCall(id=f"mock-{i}", name=tc["name"],
                         arguments=tc.get("arguments", {}))
                for i, tc in enumerate(step["tool_calls"])
            ]
            return LLMResponse(
                message=Message(role="assistant", content=step.get("content", ""), tool_calls=calls),
                stop_reason="tool_calls",
            )
        return LLMResponse(message=Message(role="assistant", content=step.get("final", "")),
                           stop_reason="stop")

    # ── internals ─────────────────────────────────────────────────────────
    def _pick(self, role: str, messages: list[Message]) -> dict[str, Any]:
        """First matching scenario, most specific first (prompt_contains > role-only > catch-all)."""
        convo = " ".join(m.content for m in messages).lower()
        candidates: list[tuple[int, dict[str, Any]]] = []
        for sc in self._scenarios:
            match = sc.get("match") or {}
            if match.get("role") and match["role"] != role:
                continue
            needle = match.get("prompt_contains")
            specificity = 2 if needle else (1 if match.get("role") else 0)
            if needle and needle.lower() not in convo:
                continue
            candidates.append((specificity, sc))
        return max(candidates, key=lambda pair: pair[0])[1] if candidates else {}

    def _next_step(self, scenario: dict[str, Any], session: str) -> dict[str, Any] | None:
        if not scenario:
            return None
        steps = scenario.get("steps") or []
        key = (scenario["_file"], session)
        idx = self._cursors.get(key, 0)
        self._cursors[key] = idx + 1
        return steps[idx] if idx < len(steps) else None

    def reset(self) -> None:
        self._cursors.clear()


def write_scenario(path: Path, data: dict[str, Any]) -> None:
    """Author a scenario file programmatically (tests use this)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
                    encoding="utf-8")


def scenario_summary(scenario_dir: Path) -> str:
    lines = []
    for sc in MockProvider(scenario_dir)._scenarios:  # noqa: SLF001 — introspection helper
        steps = len(sc.get("steps") or [])
        lines.append(f"{sc.get('_file')}: {steps} steps, match={sc.get('match')}")
    return "\n".join(lines) or "no scenarios"


def _dump_args(args: dict) -> str:  # kept for scenario authoring readability
    return json.dumps(args)
