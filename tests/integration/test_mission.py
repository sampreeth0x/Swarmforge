"""Full mock mission end-to-end: plan → swarm → verify → judge → merge."""

from __future__ import annotations

import subprocess

import pytest

from swarmforge.config import ROOT_DIR
from swarmforge.events.bus import EventBus
from swarmforge.llm.mock import MockProvider
from swarmforge.orchestrator.orchestrator import MissionRunner
from swarmforge.sandbox.local_worktree import LocalWorktreeBackend
from swarmforge.store.db import Store

SCENARIO_DIR = ROOT_DIR / "mock" / "scenarios"


@pytest.fixture()
def store(tmp_path):
    return Store(tmp_path / "mission.db")


@pytest.fixture()
def mock_llm():
    return MockProvider(SCENARIO_DIR)


class _Runner:
    """MissionRunner with pre-built mock LLM + backend (bypasses provider_factory)."""

    def __init__(self, cfg, store, bus, llm, backend) -> None:
        self._inner = MissionRunner.__new__(MissionRunner)
        self._inner.cfg = cfg
        self._inner.store = store
        self._inner.bus = bus
        self._inner.llm = llm
        self._inner.backend = backend
        self._inner.repo_dir = None

    @property
    def repo_dir(self):
        return self._inner.repo_dir

    async def run_mission(self, mid: str) -> None:
        await self._inner.run_mission(mid)


async def test_full_dark_mode_mission(store, mock_llm, tmp_path) -> None:
    bus = EventBus(store)
    backend = LocalWorktreeBackend(tmp_path / "wt", None)  # repo seeded per mission
    cfg = type("Cfg", (), {
        "mode": "mock", "model_planner": "mock", "model_worker": "mock",
        "agent_max_steps": 24, "db_path": tmp_path / "mission.db",
        "sandbox_backend": "local", "sandbox_root": tmp_path / "wt",
        "target_repo": ROOT_DIR / "examples" / "target-repo",
    })()

    mid = store.create_mission("Add dark mode support to the fixture repo", workers=2)
    runner = _Runner(cfg, store, bus, mock_llm, backend)
    await runner.run_mission(mid)

    mission = store.get_mission(mid)
    assert mission["status"] == "done", f"error: {mission['error']}"
    assert mission["result_branch"]

    events = [str(e.kind) for e in store.get_events(mid)]
    for expected in ("mission.created", "plan.ready", "task.claimed", "sandbox.created",
                     "candidate.ready", "verdict", "merge.done", "mission.done"):
        assert expected in events, f"missing {expected}; got {events}"

    # The merged branch carries the dark theme change
    out = subprocess.run(
        ["git", "-C", str(runner.repo_dir), "show",
         f"{mission['result_branch']}:static/dark.css"],
        capture_output=True, text=True, encoding="utf-8")
    assert out.returncode == 0, out.stderr
    assert "body.dark" in out.stdout

    # Candidates recorded with verdicts
    candidates = store.get_candidates(mid)
    assert candidates, "expected at least one candidate"
    assert all(c["verdict"] for c in candidates if c["tests_passed"])
