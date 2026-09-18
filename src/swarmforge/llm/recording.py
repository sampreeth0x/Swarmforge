"""RecordingProvider — wraps any real provider and writes replayable scenario YAML.

One real run against Token Factory becomes an offline-replayable mock: the
hackathon demo fallback if venue Wi-Fi dies, and a test fixture for CI.
"""

from __future__ import annotations

import json
import time
from typing import Any

import yaml

from swarmforge.llm.base import LLMResponse, Message, ToolSpec


class RecordingProvider:
    name = "recording"

    def __init__(self, inner) -> None:  # inner: LLMProvider
        self._inner = inner
        self._transcripts: list[dict[str, Any]] = []

    async def chat(self, messages: list[Message], *, tools: list[ToolSpec] | None = None,
                   model: str | None = None, temperature: float = 0.2,
                   max_tokens: int = 4096, role: str = "", session: str = "") -> LLMResponse:
        resp = await self._inner.chat(messages, tools=tools, model=model,
                                      temperature=temperature, max_tokens=max_tokens,
                                      role=role, session=session)
        self._transcripts.append({
            "role": role,
            "messages": [_m_dict(m) for m in messages],
            "response": {
                "content": resp.message.content,
                "tool_calls": [{"name": tc.name, "arguments": tc.arguments}
                               for tc in resp.message.tool_calls],
            },
            "model": model,
            "ts": time.time(),
        })
        return resp

    def save_scenarios(self, path: Any, *, role: str) -> None:
        """Write the recorded transcript for one role as a scenario file."""
        steps = []
        for t in self._transcripts:
            if t["role"] != role:
                continue
            if t["response"]["tool_calls"]:
                steps.append({"tool_calls": t["response"]["tool_calls"]})
            else:
                steps.append({"final": t["response"]["content"]})
        path = __import__("pathlib").Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump({"match": {"role": role}, "steps": steps},
                                       sort_keys=False, allow_unicode=True), encoding="utf-8")


def _m_dict(m: Message) -> dict[str, Any]:
    d: dict[str, Any] = {"role": m.role, "content": m.content}
    if m.tool_calls:
        d["tool_calls"] = [{"name": tc.name, "arguments": tc.arguments} for tc in m.tool_calls]
    return d


def load_transcripts(path: Any) -> list[dict[str, Any]]:
    return json.loads(__import__("pathlib").Path(path).read_text(encoding="utf-8"))
