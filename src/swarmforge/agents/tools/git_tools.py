"""Git tools — status, diff vs base branch, commit."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from swarmforge.llm.base import ToolSpec
from swarmforge.sandbox.base import SandboxBackend, SandboxHandle

StatusSpec = ToolSpec(
    name="git_status",
    description="Show modified/new files in your sandbox (porcelain format).",
    parameters={"type": "object", "properties": {}},
)
DiffSpec = ToolSpec(
    name="git_diff",
    description="Show your current uncommitted diff (working tree vs last commit).",
    parameters={"type": "object", "properties": {}},
)
CommitSpec = ToolSpec(
    name="git_commit",
    description="Stage everything and create a commit with the given message.",
    parameters={"type": "object", "required": ["message"],
                "properties": {"message": {"type": "string"}}},
)


def git_tools(backend: SandboxBackend, h: SandboxHandle) -> list[tuple[ToolSpec, Callable[[dict], Awaitable[str]]]]:
    async def git_status(_args: dict) -> str:
        r = await backend.exec(h, ["git", "-c", "core.autocrlf=false", "status", "--porcelain"])
        return r.stdout or "(clean)"

    async def git_diff(_args: dict) -> str:
        r = await backend.exec(h, ["git", "-c", "core.autocrlf=false", "diff"])
        return r.stdout or "(no unstaged changes)"

    async def git_commit(args: dict) -> str:
        sha = await backend.commit(h, args["message"])
        return f"committed {sha[:8]}" if sha else "nothing to commit"

    return [(StatusSpec, git_status), (DiffSpec, git_diff), (CommitSpec, git_commit)]
