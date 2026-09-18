"""Agent tool-call loop integration test: mock LLM drives real sandbox tools."""

from __future__ import annotations

from pathlib import Path

from swarmforge.agents.base import Agent, AgentConfig, AgentRole
from swarmforge.agents.tools.exec_tool import exec_tool
from swarmforge.agents.tools.fs import fs_tools
from swarmforge.agents.tools.git_tools import git_tools
from swarmforge.agents.tools.registry import ToolRegistry
from swarmforge.events.bus import EventBus
from swarmforge.llm.mock import MockProvider, write_scenario
from swarmforge.sandbox.base import SandboxSpec
from swarmforge.sandbox.fixtures import make_repo
from swarmforge.sandbox.local_worktree import LocalWorktreeBackend
from swarmforge.store.db import Store


async def test_agent_loop_writes_file_and_commits(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "seed")
    backend = LocalWorktreeBackend(tmp_path / "wt", repo)
    h = await backend.create(SandboxSpec(), label="agent-test")

    scenario_dir = tmp_path / "scenarios"
    write_scenario(scenario_dir / "w.yaml", {
        "match": {"role": "worker"},
        "steps": [
            {"tool_calls": [{"name": "write_file",
                             "arguments": {"path": "NOTES.md", "content": "written by agent"}}]},
            {"tool_calls": [{"name": "run_command",
                             "arguments": {"argv": ["python", "-c", "print('sandbox exec ok')"]}}]},
            {"tool_calls": [{"name": "git_commit",
                             "arguments": {"message": "test: agent loop"}}]},
            {"final": "done"},
        ],
    })
    mock = MockProvider(scenario_dir)

    store = Store(tmp_path / "db.sqlite")
    bus = EventBus(store)
    registry = ToolRegistry()
    for spec, fn in fs_tools(backend, h):
        registry.register(spec, fn)
    for spec, fn in exec_tool(backend, h):
        registry.register(spec, fn)
    for spec, fn in git_tools(backend, h):
        registry.register(spec, fn)

    mission_id = store.create_mission("test mission", 1)
    agent = Agent(
        AgentConfig(agent_id="w-test", role=AgentRole.WORKER, model="mock", max_steps=10),
        mission_id, mock, registry, bus, store)

    result = await agent.run("write NOTES.md and commit")
    assert result.ok and result.final_text == "done"
    assert await backend.read_file(h, "NOTES.md") == "written by agent"

    diff = await backend.diff(h)
    assert "NOTES.md" in diff

    # Events flowed: TOOL_CALLED for write_file, run_command, git_commit
    events = store.get_events(mission_id)
    kinds = [str(e.kind) for e in events]
    assert "tool.called" in kinds
    tool_names = [e.payload["tool"] for e in events if str(e.kind) == "tool.called"]
    assert tool_names == ["write_file", "run_command", "git_commit"]

    # Usage was recorded (mock reports zeros, but the agent row exists)
    agents = store.get_agents(mission_id)
    assert agents[0]["id"] == "w-test" and agents[0]["role"] == "worker"

    await backend.teardown(h)


async def test_agent_unknown_tool_becomes_tool_message(tmp_path: Path) -> None:
    scenario_dir = tmp_path / "scenarios"
    write_scenario(scenario_dir / "w.yaml", {
        "match": {}, "steps": [
            {"tool_calls": [{"name": "no_such_tool", "arguments": {}}]},
            {"final": "recovered"},
        ]})
    mock = MockProvider(scenario_dir)
    store = Store(tmp_path / "db.sqlite")
    agent = Agent(AgentConfig(agent_id="w-x", role=AgentRole.WORKER, model="mock", max_steps=5),
                  store.create_mission("m", 1), mock, ToolRegistry(), EventBus(store), store)
    result = await agent.run("whatever")
    assert result.ok and result.final_text == "recovered"
