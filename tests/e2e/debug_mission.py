"""Debug: run the mock mission and dump candidate verification state."""

import asyncio
import tempfile
from pathlib import Path

from swarmforge.config import ROOT_DIR
from swarmforge.events.bus import EventBus
from swarmforge.llm.mock import MockProvider
from swarmforge.orchestrator.orchestrator import MissionRunner
from swarmforge.sandbox.local_worktree import LocalWorktreeBackend
from swarmforge.store.db import Store

SCENARIO_DIR = ROOT_DIR / "mock" / "scenarios"


async def main() -> None:
    tmp = Path(tempfile.mkdtemp())
    store = Store(tmp / "mission.db")
    bus = EventBus(store)
    llm = MockProvider(SCENARIO_DIR)
    backend = LocalWorktreeBackend(tmp / "wt", None)
    cfg = type("Cfg", (), {
        "mode": "mock", "model_planner": "mock", "model_worker": "mock",
        "agent_max_steps": 24, "db_path": tmp / "mission.db",
        "sandbox_backend": "local", "sandbox_root": tmp / "wt",
        "target_repo": ROOT_DIR / "examples" / "target-repo",
    })()
    mid = store.create_mission("Add dark mode support to the fixture repo", workers=2)

    q = bus.subscribe(mid)
    async def watch():
        while True:
            ev = await q.get()
            print(f"[{ev.kind.value}] {ev.agent_id or '-'} {str(ev.payload)[:160]}")
            if ev.kind.value in ("mission.done", "mission.failed"):
                return

    runner = MissionRunner.__new__(MissionRunner)
    runner.cfg = cfg
    runner.store = store
    runner.bus = bus
    runner.llm = llm
    runner.backend = backend
    runner.repo_dir = None

    await asyncio.gather(runner.run_mission(mid), watch())
    print("\nmission:", store.get_mission(mid))
    for c in store.get_candidates(mid):
        print("\nCANDIDATE", c["id"], "task", c["task_id"], "passed", c["tests_passed"])
        print("  diff[:300]:", c["diff"][:300])
        print("  test_output[:500]:", c["test_output"][:500])
    for t in store.get_tasks(mid):
        print("TASK", t["id"], t["status"], t["attempts"])

if __name__ == "__main__":
    asyncio.run(main())
