"""Agent — the tool-calling loop every swarm role shares."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from swarmforge.agents.tools.registry import ToolRegistry
from swarmforge.events.bus import EventBus
from swarmforge.events.events import EventKind
from swarmforge.llm.base import LLMProvider, LLMResponse, Message
from swarmforge.store.db import Store

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
MAX_TOOL_ARGS_CHARS = 800


class AgentRole(StrEnum):
    PLANNER = "planner"
    WORKER = "worker"
    VERIFIER = "verifier"
    JUDGE = "judge"
    MERGER = "merger"


@dataclass(slots=True)
class AgentConfig:
    agent_id: str
    role: AgentRole
    model: str
    temperature: float = 0.2
    max_steps: int = 24
    system_prompt: str = ""


@dataclass(slots=True)
class AgentResult:
    agent_id: str
    final_text: str
    ok: bool = True
    steps: int = 0
    error: str | None = None


class Agent:
    def __init__(self, cfg: AgentConfig, mission_id: str, llm: LLMProvider,
                 tools: ToolRegistry, bus: EventBus, store: Store) -> None:
        self.cfg = cfg
        self.mission_id = mission_id
        self.llm = llm
        self.tools = tools
        self.bus = bus
        self.store = store
        if not cfg.system_prompt:
            cfg.system_prompt = (PROMPTS_DIR / f"{cfg.role}.md").read_text(encoding="utf-8")
        self.store.upsert_agent(cfg.agent_id, mission_id, cfg.role, cfg.model)

    async def run(self, task: str, context: dict[str, Any] | None = None,
                  should_stop: Callable[[], bool] | None = None) -> AgentResult:
        """Run the tool-calling loop to completion. `should_stop` ends the loop
        after a tool batch (e.g. the worker called submit_candidate)."""
        context = context or {}
        messages: list[Message] = [
            Message(role="system", content=self.cfg.system_prompt),
            Message(role="user", content=f"# Task\n{task}\n\n# Context\n{_format_context(context)}"),
        ]
        self.store.update_agent(self.cfg.agent_id, status="running")

        for step in range(1, self.cfg.max_steps + 1):
            await self.bus.publish(
                EventKind.AGENT_STEP, self.mission_id,
                {"agent_id": self.cfg.agent_id, "role": self.cfg.role, "step": step},
                agent_id=self.cfg.agent_id)

            resp: LLMResponse = await self.llm.chat(
                messages, tools=self.tools.specs(), model=self.cfg.model,
                temperature=self.cfg.temperature, role=self.cfg.role,
                session=f"{self.mission_id}:{self.cfg.agent_id}")
            await self._account(resp)

            if resp.message.tool_calls:
                messages.append(resp.message)
                for tc in resp.message.tool_calls:
                    await self.bus.publish(
                        EventKind.TOOL_CALLED, self.mission_id,
                        {"agent_id": self.cfg.agent_id, "tool": tc.name,
                         "arguments": _truncate_obj(tc.arguments, MAX_TOOL_ARGS_CHARS)},
                        agent_id=self.cfg.agent_id)
                    result = await self.tools.dispatch(tc)
                    await self.bus.publish(
                        EventKind.TOOL_RESULT, self.mission_id,
                        {"agent_id": self.cfg.agent_id, "tool": tc.name,
                         "result": result[:1000]},
                        agent_id=self.cfg.agent_id)
                    messages.append(Message(role="tool", content=result,
                                            tool_call_id=tc.id, name=tc.name))
                if should_stop is not None and should_stop():
                    self.store.update_agent(self.cfg.agent_id, status="done")
                    return AgentResult(agent_id=self.cfg.agent_id,
                                       final_text="[submitted]", ok=True, steps=step)
                continue

            self.store.update_agent(self.cfg.agent_id, status="done")
            return AgentResult(agent_id=self.cfg.agent_id, final_text=resp.message.content,
                               ok=True, steps=step)

        self.store.update_agent(self.cfg.agent_id, status="max_steps")
        return AgentResult(agent_id=self.cfg.agent_id,
                           final_text="[max steps reached without a final answer]",
                           ok=False, steps=self.cfg.max_steps, error="max_steps")

    async def _account(self, resp: LLMResponse) -> None:
        u = resp.usage
        self.store.add_usage(self.cfg.agent_id, u.prompt_tokens, u.completion_tokens,
                             u.cost_usd, 1)
        if u.prompt_tokens or u.completion_tokens:
            await self.bus.publish(
                EventKind.USAGE, self.mission_id,
                {"agent_id": self.cfg.agent_id, "prompt_tokens": u.prompt_tokens,
                 "completion_tokens": u.completion_tokens, "cost_usd": round(u.cost_usd, 6)},
                agent_id=self.cfg.agent_id)


def _format_context(context: dict[str, Any]) -> str:
    if not context:
        return "(none)"
    return "\n".join(f"## {k}\n{_truncate_obj(v, 2000)}" for k, v in context.items())


def _truncate_obj(v: Any, limit: int) -> Any:
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)
    return s if len(s) <= limit else s[:limit] + "…"
