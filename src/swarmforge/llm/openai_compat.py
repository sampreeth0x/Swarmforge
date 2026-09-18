"""OpenAI-compatible chat-completions provider — used for both Nebius Token Factory and NVIDIA NIM."""

from __future__ import annotations

import json
from typing import Any

import httpx

from swarmforge.llm.base import LLMResponse, Message, ToolCall, ToolSpec, Usage, estimate_cost


class OpenAICompatProvider:
    """POSTs to {base_url}/chat/completions with tool-calling support."""

    def __init__(self, base_url: str, api_key: str, name: str = "openai-compat",
                 timeout_s: float = 120.0) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
            timeout=timeout_s,
        )

    async def chat(self, messages: list[Message], *, tools: list[ToolSpec] | None = None,
                   model: str | None = None, temperature: float = 0.2,
                   max_tokens: int = 4096, role: str = "", session: str = "") -> LLMResponse:
        payload: dict[str, Any] = {
            "model": model or "nemotron-3-nano-30b-a3b",
            "messages": [_wire_message(m) for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = [
                {"type": "function",
                 "function": {"name": t.name, "description": t.description,
                              "parameters": t.parameters}}
                for t in tools
            ]

        resp = await self._client.post("/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()

        choice = data["choices"][0]
        raw_msg = choice.get("message", {})
        tool_calls = [
            ToolCall(id=tc["id"], name=tc["function"]["name"],
                     arguments=_parse_args(tc["function"].get("arguments", "{}")))
            for tc in raw_msg.get("tool_calls") or []
        ]
        usage_d = data.get("usage") or {}
        usage = Usage(
            prompt_tokens=usage_d.get("prompt_tokens", 0),
            completion_tokens=usage_d.get("completion_tokens", 0),
            cost_usd=estimate_cost(payload["model"], usage_d.get("prompt_tokens", 0),
                                   usage_d.get("completion_tokens", 0)),
        )
        stop = choice.get("finish_reason", "stop")
        stop_reason = "tool_calls" if stop == "tool_calls" and tool_calls else stop
        return LLMResponse(
            message=Message(role="assistant", content=raw_msg.get("content") or "",
                            tool_calls=tool_calls),
            stop_reason=stop_reason,
            usage=usage,
        )

    async def list_models(self) -> list[str]:
        resp = await self._client.get("/models")
        resp.raise_for_status()
        return [m["id"] for m in resp.json().get("data", [])]

    async def aclose(self) -> None:
        await self._client.aclose()


def _wire_message(m: Message) -> dict[str, Any]:
    msg: dict[str, Any] = {"role": m.role, "content": m.content}
    if m.role == "tool":
        msg = {"role": "tool", "content": m.content, "tool_call_id": m.tool_call_id or ""}
    elif m.tool_calls:
        msg["tool_calls"] = [
            {"id": tc.id, "type": "function",
             "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)}}
            for tc in m.tool_calls
        ]
    return msg


def _parse_args(raw: str | dict) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return {"_raw": raw}
