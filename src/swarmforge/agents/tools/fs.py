"""Filesystem tools — bound to one sandbox."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

from swarmforge.llm.base import ToolSpec
from swarmforge.sandbox.base import SandboxBackend, SandboxHandle

ReadSpec = ToolSpec(
    name="read_file",
    description="Read a file from your sandbox. Returns its full text.",
    parameters={"type": "object", "required": ["path"],
                "properties": {"path": {"type": "string", "description": "relative path"}}},
)
WriteSpec = ToolSpec(
    name="write_file",
    description="Create or overwrite a file in your sandbox with the given text content.",
    parameters={"type": "object", "required": ["path", "content"],
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}}},
)
ListSpec = ToolSpec(
    name="list_files",
    description="List files in a directory of your sandbox (default: repo root).",
    parameters={"type": "object",
                "properties": {"path": {"type": "string", "description": "default '.'"}}},
)


def fs_tools(backend: SandboxBackend, h: SandboxHandle) -> list[tuple[ToolSpec, Callable[[dict], Awaitable[str]]]]:
    async def read_file(args: dict) -> str:
        return await backend.read_file(h, args["path"])

    async def write_file(args: dict) -> str:
        await backend.write_file(h, args["path"], args["content"])
        return f"wrote {args['path']} ({len(args['content'])} chars)"

    async def list_files(args: dict) -> str:
        return json.dumps(await backend.list_files(h, args.get("path", ".")))

    return [(ReadSpec, read_file), (WriteSpec, write_file), (ListSpec, list_files)]
