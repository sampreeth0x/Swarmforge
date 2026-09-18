"""MockProvider unit tests: scenario matching, per-session cursors, determinism."""

from __future__ import annotations

from pathlib import Path

from swarmforge.llm.base import Message
from swarmforge.llm.mock import MockProvider, write_scenario


def _make_provider(tmp_path: Path, scenarios: dict[str, dict]) -> MockProvider:
    for name, data in scenarios.items():
        write_scenario(tmp_path / f"{name}.yaml", data)
    return MockProvider(tmp_path)


async def test_scenario_selection_by_role(tmp_path) -> None:
    p = _make_provider(tmp_path, {
        "worker": {"match": {"role": "worker"},
                   "steps": [{"final": "worker answer"}]},
        "planner": {"match": {"role": "planner"},
                    "steps": [{"final": '{"plan": []}'}]},
    })
    r = await p.chat([Message(role="user", content="task")], role="worker")
    assert r.message.content == "worker answer"
    r = await p.chat([Message(role="user", content="task")], role="planner")
    assert '"plan"' in r.message.content


async def test_prompt_contains_match_beats_catchall(tmp_path) -> None:
    p = _make_provider(tmp_path, {
        "catchall": {"match": {"role": "worker"}, "steps": [{"final": "generic"}]},
        "specific": {"match": {"role": "worker", "prompt_contains": "dark mode"},
                     "steps": [{"final": "dark mode specialist"}]},
    })
    # Files load alphabetically: catchall before specific — matching must still prefer specific
    r = await p.chat([Message(role="user", content="add dark mode please")], role="worker")
    assert r.message.content == "dark mode specialist"


async def test_per_session_cursors_are_independent(tmp_path) -> None:
    p = _make_provider(tmp_path, {
        "s": {"match": {"role": "worker"},
              "steps": [{"final": "step-1"}, {"final": "step-2"}]},
    })
    r1a = await p.chat([Message(role="user", content="t")], role="worker", session="agent-1")
    r1b = await p.chat([Message(role="user", content="t")], role="worker", session="agent-1")
    r2a = await p.chat([Message(role="user", content="t")], role="worker", session="agent-2")
    assert r1a.message.content == "step-1"
    assert r1b.message.content == "step-2"
    assert r2a.message.content == "step-1"  # fresh session restarts the script


async def test_exhausted_scenario_returns_stop(tmp_path) -> None:
    p = _make_provider(tmp_path, {"s": {"match": {}, "steps": [{"final": "only"}]}})
    await p.chat([], role="worker", session="a")
    r = await p.chat([], role="worker", session="a")
    assert r.stop_reason == "stop"
