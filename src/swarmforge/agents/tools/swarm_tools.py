"""Swarm-level tools — fork_sandbox, submit_candidate.

These close over orchestrator callbacks so the worker can fork its own sandbox
mid-task (the Contree branching showcase) and hand a candidate to the swarm.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from swarmforge.llm.base import ToolSpec
from swarmforge.sandbox.base import SandboxBackend, SandboxHandle

ForkSpec = ToolSpec(
    name="fork_sandbox",
    description=("Fork your sandbox into a second sandbox branching from your current state. "
                 "Use it to try a second approach in parallel without losing this one."),
    parameters={"type": "object", "required": ["label"],
                "properties": {"label": {"type": "string", "description": "short name for the fork"}}},
)
SubmitSpec = ToolSpec(
    name="submit_candidate",
    description=("Commit your work and submit it as a candidate solution for your task. "
                 "Call this when you are done; include a one-line summary."),
    parameters={"type": "object", "required": ["summary"],
                "properties": {"summary": {"type": "string"}}},
)


def swarm_tools(
    backend: SandboxBackend,
    h: SandboxHandle,
    on_fork: Callable[[SandboxHandle], Awaitable[SandboxHandle]],
    on_submit: Callable[[SandboxHandle, str], Awaitable[str]],
) -> list[tuple[ToolSpec, Callable[[dict], Awaitable[str]]]]:
    async def fork_sandbox(args: dict) -> str:
        child = await on_fork(h, args["label"])
        return (f"forked new sandbox {child.id} (branch {child.branch}). "
                f"You are still in sandbox {h.id}; the fork is a separate workspace.")

    async def submit_candidate(args: dict) -> str:
        return await on_submit(h, args["summary"])

    return [(ForkSpec, fork_sandbox), (SubmitSpec, submit_candidate)]
