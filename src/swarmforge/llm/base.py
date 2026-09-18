"""LLM provider abstractions — one Protocol, three implementations (tokenfactory, nim, mock)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

Role = Literal["system", "user", "assistant", "tool"]


@dataclass(slots=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Message:
    role: Role
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None  # set on role="tool" messages
    name: str | None = None          # tool name on role="tool" messages


@dataclass(slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema


@dataclass(slots=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0


@dataclass(slots=True)
class LLMResponse:
    message: Message
    stop_reason: str  # "stop" | "tool_calls" | "length" | "error"
    usage: Usage = field(default_factory=Usage)


class LLMProvider(Protocol):
    name: str

    async def chat(self, messages: list[Message], *, tools: list[ToolSpec] | None = None,
                   model: str | None = None, temperature: float = 0.2,
                   max_tokens: int = 4096, role: str = "", session: str = "") -> LLMResponse: ...


# ── cost accounting ──────────────────────────────────────────────────────
# USD per million tokens; unknown models cost $0 (usage still tracked).
PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    # model_id: (input $/Mtok, output $/Mtok) — verify at deploy time
    "nemotron-3-super-120b-a12b": (0.12, 0.60),
    "nemotron-3-nano-30b-a3b": (0.03, 0.15),
}


def estimate_cost(model: str | None, prompt_tokens: int, completion_tokens: int) -> float:
    prices = PRICES_PER_MTOK.get(model or "", (0.0, 0.0))
    return prompt_tokens / 1e6 * prices[0] + completion_tokens / 1e6 * prices[1]


def provider_factory(name: str, config) -> LLMProvider:
    if name == "mock":
        from swarmforge.llm.mock import MockProvider

        return MockProvider(scenario_dir=config.scenario_dir)
    if name == "tokenfactory":
        from swarmforge.llm.openai_compat import OpenAICompatProvider

        return OpenAICompatProvider(base_url=config.llm_base_url, api_key=config.nebius_api_key,
                                    name="tokenfactory")
    if name == "nim":
        from swarmforge.llm.openai_compat import OpenAICompatProvider

        return OpenAICompatProvider(base_url=config.nim_base_url, api_key=config.nim_api_key,
                                    name="nim")
    raise ValueError(f"unknown LLM provider mode: {name!r}")
