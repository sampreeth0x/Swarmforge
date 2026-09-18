"""Worker pool — claims READY tasks atomically and runs one agent per task in its own sandbox."""

from __future__ import annotations

import asyncio
import logging

from swarmforge.agents.base import Agent, AgentConfig, AgentRole
from swarmforge.agents.tools.exec_tool import exec_tool
from swarmforge.agents.tools.fs import fs_tools
from swarmforge.agents.tools.git_tools import git_tools
from swarmforge.agents.tools.registry import ToolRegistry
from swarmforge.agents.tools.swarm_tools import swarm_tools
from swarmforge.events.bus import EventBus
from swarmforge.events.events import EventKind
from swarmforge.llm.base import LLMProvider
from swarmforge.sandbox.base import SandboxBackend, SandboxHandle, SandboxSpec
from swarmforge.store.db import Store

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 2
POLL_INTERVAL_S = 0.25


class WorkerPool:
    def __init__(self, mission_id: str, backend: SandboxBackend, llm: LLMProvider,
                 bus: EventBus, store: Store, *, worker_model: str, max_workers: int = 4,
                 agent_max_steps: int = 24, base_branch: str = "main") -> None:
        self.mid = mission_id
        self.backend = backend
        self.llm = llm
        self.bus = bus
        self.store = store
        self.worker_model = worker_model
        self.max_workers = max_workers
        self.agent_max_steps = agent_max_steps
        self.base_branch = base_branch

    async def run_until_done(self) -> None:
        """Schedule up to max_workers concurrent workers until all tasks settle."""
        inflight: set[asyncio.Task] = set()
        try:
            while True:
                self._promote_ready_tasks()
                tasks = self.store.get_tasks(self.mid)
                if all(t["status"] in ("done", "failed") for t in tasks):
                    break

                while len(inflight) < self.max_workers:
                    claimed = self.store.claim_ready_task(self.mid, agent_id="pending")
                    if claimed is None:
                        break
                    agent_id = f"w-{claimed['id']}-a{claimed['attempts']}"
                    self.store.update_task(claimed["id"], status="running",
                                           assigned_agent=agent_id)
                    await self.bus.publish(EventKind.TASK_CLAIMED, self.mid,
                                           {"task_id": claimed["id"], "title": claimed["title"],
                                            "agent_id": agent_id})
                    t = asyncio.create_task(self._run_worker(claimed, agent_id))
                    inflight.add(t)
                    t.add_done_callback(inflight.discard)

                if not inflight:
                    remaining = [t for t in tasks if t["status"] not in ("done", "failed")]
                    if remaining:
                        raise RuntimeError(
                            f"task deadlock; no runnable tasks: {[t['id'] for t in remaining]}")
                    break
                await asyncio.sleep(POLL_INTERVAL_S)
            if inflight:
                await asyncio.gather(*inflight)
        finally:
            for t in inflight:
                t.cancel()

    def _promote_ready_tasks(self) -> None:
        """PENDING tasks whose deps are all DONE become READY (claimable)."""
        tasks = self.store.get_tasks(self.mid)
        done = {t["id"] for t in tasks if t["status"] == "done"}
        for t in tasks:
            if t["status"] == "pending" and all(d in done for d in t["depends_on"]):
                self.store.update_task(t["id"], status="ready")

    # ── one worker = one agent = one sandbox ──────────────────────────────
    async def _run_worker(self, task: dict, agent_id: str) -> None:
        label = f"m{self.mid}-t{task['id']}"
        h = await self.backend.create(SandboxSpec(base_ref=self.base_branch), label=label)
        await self.bus.publish(EventKind.SANDBOX_CREATED, self.mid,
                               {"sandbox": h.id, "agent_id": agent_id, "task_id": task["id"],
                                "branch": h.branch, "label": label})
        submitted = asyncio.Event()  # per-worker: never shared across the pool

        registry = self._build_registry(h, task, submitted)
        agent = Agent(
            AgentConfig(agent_id=agent_id, role=AgentRole.WORKER, model=self.worker_model,
                        max_steps=self.agent_max_steps),
            self.mid, self.llm, registry, self.bus, self.store)

        try:
            result = await agent.run(task["instructions"], context={
                "task_id": task["id"],
                "title": task["title"],
                "acceptance_criteria": task["acceptance_criteria"],
                "files_you_may_touch": task["files_touched"] or "(your task defines the scope)",
            }, should_stop=submitted.is_set)

            if submitted.is_set:
                self.store.update_task(task["id"], status="done")
            else:
                await self._retry_or_fail(task, f"worker ended without submitting: {result.error}")
        except Exception as exc:  # noqa: BLE001 — a worker crash must not kill the swarm
            log.exception("worker %s crashed", agent_id)
            await self._retry_or_fail(task, f"worker crashed: {exc}")
        finally:
            await self.backend.teardown(h)

    def _build_registry(self, h: SandboxHandle, task: dict,
                        submitted: asyncio.Event) -> ToolRegistry:
        reg = ToolRegistry()
        for spec, fn in fs_tools(self.backend, h):
            reg.register(spec, fn)
        for spec, fn in exec_tool(self.backend, h):
            reg.register(spec, fn)
        for spec, fn in git_tools(self.backend, h):
            reg.register(spec, fn)

        task_id = task["id"]

        async def on_fork(parent: SandboxHandle, label: str) -> SandboxHandle:
            child = await self.backend.fork(parent, label=label)
            await self.bus.publish(EventKind.SANDBOX_FORKED, self.mid,
                                   {"parent": parent.id, "child": child.id,
                                    "branch": child.branch, "task_id": task_id})
            return child

        async def on_submit(handle: SandboxHandle, summary: str) -> str:
            await self.backend.commit(handle, summary)
            patch = await self.backend.export_patch(handle, task_id=task_id, agent_id=handle.id)
            cid = self.store.create_candidate(self.mid, task_id=task_id, agent_id=handle.id,
                                              diff=patch.diff, commit_message=summary,
                                              stats=patch.stats)
            await self.bus.publish(EventKind.CANDIDATE_READY, self.mid,
                                   {"candidate_id": cid, "task_id": task_id,
                                    "agent_id": handle.id, "summary": summary,
                                    "stats": patch.stats})
            submitted.set()
            return (f"candidate {cid} submitted and locked in. "
                    "Stop working; a final summary sentence is enough.")

        for spec, fn in swarm_tools(self.backend, h, on_fork=on_fork, on_submit=on_submit):
            reg.register(spec, fn)
        return reg

    async def _retry_or_fail(self, task: dict, reason: str) -> None:
        attempts = task.get("attempts", 1)
        if attempts < MAX_ATTEMPTS:
            self.store.update_task(task["id"], status="ready", attempts=attempts + 1)
            await self.bus.publish(EventKind.AGENT_STEP, self.mid,
                                   {"task_id": task["id"], "retrying": True,
                                    "reason": reason[:200]})
        else:
            self.store.update_task(task["id"], status="failed")
