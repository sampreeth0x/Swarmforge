"""Merge arena — backend-agnostic git-layer merging of winning candidate patches.

Contree has no merge API; local worktrees don't need one. Merging happens once,
at the git layer: apply winners in order with `git apply --3way`, re-run tests
after every apply, and hand conflicts to the merger agent.
"""

from __future__ import annotations

import logging

from swarmforge.agents.base import Agent, AgentConfig, AgentRole
from swarmforge.agents.tools.exec_tool import exec_tool
from swarmforge.agents.tools.fs import fs_tools
from swarmforge.agents.tools.git_tools import git_tools
from swarmforge.agents.tools.registry import ToolRegistry
from swarmforge.events.bus import EventBus
from swarmforge.events.events import EventKind
from swarmforge.llm.base import LLMProvider
from swarmforge.sandbox.base import SandboxBackend, SandboxHandle, SandboxSpec
from swarmforge.store.db import Store

log = logging.getLogger(__name__)

PATCH_FILENAME = "_swarmforge_candidate.patch"


class Merger:
    def __init__(self, backend: SandboxBackend, llm: LLMProvider, bus: EventBus, store: Store,
                 *, merger_model: str, base_branch: str = "main") -> None:
        self.backend = backend
        self.llm = llm
        self.bus = bus
        self.store = store
        self.merger_model = merger_model
        self.base_branch = base_branch

    async def merge(self, mission_id: str, winners: list[dict]) -> dict:
        """Apply winners onto a fresh arena branch. Returns {branch, merged, dropped}."""
        arena = await self.backend.create(SandboxSpec(base_ref=self.base_branch),
                                          label=f"arena-{mission_id}")
        merged: list[str] = []
        dropped: list[dict] = []
        try:
            for c in sorted(winners, key=lambda x: x["task_id"]):
                ok = await self._apply_candidate(mission_id, arena, c)
                if ok:
                    merged.append(c["id"])
                else:
                    dropped.append(c["id"])

            final_tests = await self.backend.exec(arena, ["python", "-m", "pytest", "tests/", "-q"],
                                                  timeout_s=300)
            await self.backend.commit(arena, f"swarm mission {mission_id}: merge "
                                             f"{', '.join(merged) or 'no candidates'}")
            if not final_tests.ok:
                await self.bus.publish(EventKind.TESTS_FAILED, mission_id,
                                       {"stage": "post-merge", "output": final_tests.stdout[-1500:]})
            await self.bus.publish(EventKind.MERGE_DONE, mission_id,
                                   {"branch": arena.branch, "merged": merged, "dropped": dropped,
                                    "tests_passed": final_tests.ok})
            return {"branch": arena.branch, "merged": merged, "dropped": dropped,
                    "tests_passed": final_tests.ok}
        finally:
            if not merged:
                await self.backend.teardown(arena)

    async def _apply_candidate(self, mission_id: str, arena: SandboxHandle, c: dict) -> bool:
        await self.backend.write_file(arena, PATCH_FILENAME, c.get("diff") or "")
        apply_r = await self.backend.exec(
            arena, ["git", "-c", "core.autocrlf=false", "apply", "--3way", PATCH_FILENAME])
        await self.backend.exec(arena, ["git", "add", "-A"])  # stage regardless of conflict state

        if apply_r.ok:
            test_r = await self.backend.exec(arena, ["python", "-m", "pytest", "tests/", "-q"],
                                             timeout_s=300)
            if test_r.ok:
                return True
            # Applied cleanly but broke tests → roll back and drop
            await self._reset_arena(arena)
            await self.bus.publish(EventKind.MERGE_CONFLICT, mission_id,
                                   {"candidate_id": c["id"], "kind": "tests_failed",
                                    "output": test_r.stdout[-1000:]})
            return False

        # Conflicted hunks → hand to the merger agent
        await self.bus.publish(EventKind.MERGE_CONFLICT, mission_id,
                               {"candidate_id": c["id"], "kind": "conflict_markers",
                                "output": apply_r.stderr[-1000:]})
        resolved = await self._agent_resolve(mission_id, arena, c, apply_r.stderr)
        if resolved:
            return True
        await self._reset_arena(arena)
        return False

    async def _agent_resolve(self, mission_id: str, arena: SandboxHandle, c: dict,
                             conflict_output: str) -> bool:
        agent = Agent(
            AgentConfig(agent_id=f"merger-{c['id']}", role=AgentRole.MERGER,
                        model=self.merger_model, max_steps=12),
            mission_id, self.llm, self._registry(arena), self.bus, self.store)
        result = await agent.run(
            f"Resolve the merge conflict left by candidate {c['id']} in the arena.",
            context={"git_apply_stderr": conflict_output[-2000:],
                     "candidate_summary": c.get("commit_message", "")})
        if not result.ok:
            return False
        test_r = await self.backend.exec(arena, ["python", "-m", "pytest", "tests/", "-q"],
                                         timeout_s=300)
        if test_r.ok:
            await self.backend.commit(arena, f"merge candidate {c['id']} (conflict resolved)")
            return True
        await self.bus.publish(EventKind.MERGE_CONFLICT, mission_id,
                               {"candidate_id": c["id"], "kind": "resolution_failed_tests",
                                "output": test_r.stdout[-1000:]})
        return False

    def _registry(self, h: SandboxHandle) -> ToolRegistry:
        reg = ToolRegistry()
        for spec, fn in fs_tools(self.backend, h):
            reg.register(spec, fn)
        for spec, fn in exec_tool(self.backend, h):
            reg.register(spec, fn)
        for spec, fn in git_tools(self.backend, h):
            reg.register(spec, fn)
        return reg

    async def _reset_arena(self, arena: SandboxHandle) -> None:
        await self.backend.exec(arena, ["git", "reset", "--hard", self.base_branch])
        await self.backend.exec(arena, ["git", "clean", "-fd"])
