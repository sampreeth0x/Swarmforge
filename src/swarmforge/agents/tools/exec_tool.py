"""Command-execution tool — runs commands inside the agent's sandbox."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

from swarmforge.llm.base import ToolSpec
from swarmforge.sandbox.base import SandboxBackend, SandboxHandle

RunSpec = ToolSpec(
    name="run_command",
    description="Run a shell command in your sandbox working directory and get exit code, stdout, stderr.",
    parameters={"type": "object", "required": ["argv"],
                "properties": {
                    "argv": {"type": "array", "items": {"type": "string"},
                             "description": "command as argv list, e.g. [\"python\", \"-m\", \"pytest\", \"-q\"]"},
                    "timeout_s": {"type": "integer", "description": "default 600"},
                }},
)

MAX_OUTPUT_CHARS = 6000


def exec_tool(backend: SandboxBackend, h: SandboxHandle) -> list[tuple[ToolSpec, Callable[[dict], Awaitable[str]]]]:
    async def run_command(args: dict) -> str:
        argv = args["argv"]
        if not isinstance(argv, list) or not all(isinstance(a, str) for a in argv):
            return "ERROR: argv must be a list of strings"
        r = await backend.exec(h, argv, timeout_s=int(args.get("timeout_s", 600)))
        return json.dumps({"exit_code": r.exit_code,
                           "stdout": r.stdout[:MAX_OUTPUT_CHARS],
                           "stderr": r.stderr[:MAX_OUTPUT_CHARS]})

    return [(RunSpec, run_command)]
