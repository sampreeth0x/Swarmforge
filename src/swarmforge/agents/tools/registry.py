"""ToolRegistry — JSON-Schema tool specs mapped to async dispatch callables."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from swarmforge.llm.base import ToolCall, ToolSpec

MAX_TOOL_RESULT_CHARS = 8000

ToolFn = Callable[[dict[str, Any]], Awaitable[str]]


class ToolRegistry:
    def __init__(self, max_result_chars: int = MAX_TOOL_RESULT_CHARS) -> None:
        self._tools: dict[str, tuple[ToolSpec, ToolFn]] = {}
        self._max_result = max_result_chars

    def register(self, spec: ToolSpec, fn: ToolFn) -> None:
        if spec.name in self._tools:
            raise ValueError(f"duplicate tool: {spec.name}")
        self._tools[spec.name] = (spec, fn)

    def specs(self) -> list[ToolSpec]:
        return [spec for spec, _ in self._tools.values()]

    def names(self) -> list[str]:
        return list(self._tools)

    async def dispatch(self, call: ToolCall) -> str:
        if call.name not in self._tools:
            return f"ERROR: unknown tool {call.name!r}. Available: {self.names()}"
        _spec, fn = self._tools[call.name]
        try:
            result = await fn(call.arguments)
        except Exception as exc:  # tool failures become tool messages, never crash the loop
            return f"ERROR: {type(exc).__name__}: {exc}"
        result = _as_text(result)
        if len(result) > self._max_result:
            head = result[: self._max_result]
            return f"{head}\n…[truncated {len(result) - self._max_result} chars]"
        return result

    def dump(self) -> str:
        return json.dumps({s.name: s.description for s in self.specs()}, indent=2)


def _as_text(result: Any) -> str:
    if isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=False, default=str)
