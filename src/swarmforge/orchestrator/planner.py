"""Planner — one Nemotron call decomposes the request into a validated plan DAG."""

from __future__ import annotations

from swarmforge.agents.base import Agent, AgentConfig, AgentRole
from swarmforge.agents.tools.registry import ToolRegistry
from swarmforge.events.bus import EventBus
from swarmforge.llm.base import LLMProvider
from swarmforge.orchestrator.mission import Plan, PlanError, parse_plan
from swarmforge.store.db import Store

MAX_REPAIR_ROUNDS = 1


class Planner:
    def __init__(self, llm: LLMProvider, bus: EventBus, store: Store,
                 model: str, max_steps: int = 8) -> None:
        self.llm = llm
        self.bus = bus
        self.store = store
        self.model = model
        self.max_steps = max_steps

    async def plan(self, mission_id: str, request: str) -> Plan:
        agent = Agent(
            AgentConfig(agent_id="planner", role=AgentRole.PLANNER, model=self.model,
                        max_steps=self.max_steps),
            mission_id, self.llm, ToolRegistry(), self.bus, self.store)

        result = await agent.run(request)
        if not result.ok:
            raise PlanError(f"planner did not finish: {result.error}")
        try:
            return parse_plan(result.final_text)
        except PlanError as exc:
            # One repair round-trip: show the model its own invalid output.
            repair = await agent.run(
                f"Your plan was invalid: {exc}\nRe-output ONLY the corrected JSON plan object.",
                context={"previous_output": result.final_text})
            if not repair.ok:
                raise PlanError(f"planner repair failed: {repair.error}") from exc
            try:
                return parse_plan(repair.final_text)
            except PlanError as exc2:
                raise PlanError(f"plan invalid after repair: {exc2}") from exc2
