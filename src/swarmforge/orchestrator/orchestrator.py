"""MissionRunner — drives one mission through the full state machine."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from swarmforge.config import Config
from swarmforge.events.bus import EventBus
from swarmforge.events.events import EventKind
from swarmforge.llm.base import provider_factory, recording_of, wrap_recording
from swarmforge.orchestrator.judge import Judge
from swarmforge.orchestrator.merger import Merger
from swarmforge.orchestrator.planner import Planner
from swarmforge.orchestrator.verifier import Verifier
from swarmforge.orchestrator.workers import WorkerPool
from swarmforge.sandbox.base import backend_factory
from swarmforge.sandbox.fixtures import make_repo

log = logging.getLogger(__name__)


class MissionRunner:
    def __init__(self, config: Config, store, bus: EventBus, repo_dir: Path | None = None) -> None:
        self.cfg = config
        self.store = store
        self.bus = bus
        self.llm = wrap_recording(provider_factory(config.mode, config), config)
        self.repo_dir = repo_dir  # local backends: lazily seeded per mission
        if config.sandbox_backend == "local":
            self.backend = backend_factory("local", root_dir=config.sandbox_root,
                                           repo_dir=repo_dir)
        else:
            self.backend = backend_factory(
                "contree", base_url=config.sandboxes_base_url,
                iam_token=config.nebius_iam_token,
                project_id=config.nebius_project_id,
                base_image=config.contree_base_image)

    async def run_mission(self, mission_id: str) -> None:
        mission = self.store.get_mission(mission_id)
        if mission is None:
            raise ValueError(f"unknown mission {mission_id}")
        request = mission["request"]
        workers = mission["workers"]
        log.info("mission %s starting: %r", mission_id, request[:80])

        try:
            await self.bus.publish(EventKind.MISSION_CREATED, mission_id,
                                   {"request": request, "workers": workers})
            # ── planning ─────────────────────────────────────────────────
            self.store.update_mission(mission_id, status="planning")
            planner = Planner(self.llm, self.bus, self.store, model=self.cfg.model_planner)
            plan = await planner.plan(mission_id, request)
            task_ids = self._persist_plan(mission_id, plan)
            await self.bus.publish(EventKind.PLAN_READY, mission_id,
                                   {"tasks": task_ids, "titles": [s.title for s in plan.subtasks]})
            self.store.update_mission(mission_id, status="spawning")

            # ── seed repo + sandbox backend (local mode seeds per mission) ─
            repo_dir = self.repo_dir or make_repo(self._mission_dir(mission_id) / "repo")
            self.repo_dir = repo_dir
            if getattr(self.backend, "repo_dir", None) is None:
                self.backend.repo_dir = repo_dir  # local backend
            if getattr(self.backend, "name", "") == "contree":
                self.backend.repo_source = repo_dir
            self.store.update_mission(mission_id, status="executing")

            # ── executing: the swarm races ────────────────────────────────
            pool = WorkerPool(mission_id, self.backend, self.llm, self.bus, self.store,
                              worker_model=self.cfg.model_worker,
                              max_workers=workers,
                              agent_max_steps=self.cfg.agent_max_steps)
            await pool.run_until_done()

            tasks = self.store.get_tasks(mission_id)
            failed = [t for t in tasks if t["status"] == "failed"]
            candidates = self.store.get_candidates(mission_id)
            if not candidates or len(failed) == len(tasks):
                raise RuntimeError(f"mission produced no viable candidates "
                                   f"({len(failed)} failed tasks)")

            # ── verifying ─────────────────────────────────────────────────
            self.store.update_mission(mission_id, status="verifying")
            verifier = Verifier(self.backend, self.llm, self.bus, self.store,
                                verifier_model=self.cfg.model_worker)
            verified = await verifier.verify_all(mission_id, candidates)

            # ── judging ───────────────────────────────────────────────────
            self.store.update_mission(mission_id, status="judging")
            judge = Judge(self.llm, self.bus, self.store, judge_model=self.cfg.model_planner)
            winners = await judge.judge(mission_id, verified)
            if not winners:
                raise RuntimeError("no passing candidates after verification")

            # ── merging ───────────────────────────────────────────────────
            self.store.update_mission(mission_id, status="merging")
            merger = Merger(self.backend, self.llm, self.bus, self.store,
                            merger_model=self.cfg.model_planner)
            result = await merger.merge(mission_id, winners)
            self.store.update_mission(mission_id, status="done",
                                      result_branch=result["branch"])
            await self.bus.publish(EventKind.MISSION_DONE, mission_id,
                                   {"branch": result["branch"], "merged": result["merged"],
                                    "dropped": result["dropped"]})
            log.info("mission %s done → %s", mission_id, result["branch"])

        except Exception as exc:  # noqa: BLE001 — mission failures are terminal events
            log.exception("mission %s failed", mission_id)
            self.store.update_mission(mission_id, status="failed", error=str(exc)[:500])
            await self.bus.publish(EventKind.MISSION_FAILED, mission_id,
                                   {"error": str(exc)[:500]})
        finally:
            self._save_recording(mission_id)

    def _save_recording(self, mission_id: str) -> None:
        """Persist recorded LLM transcripts as replayable mock scenarios, if recording."""
        rec = recording_of(self.llm)
        if rec is None or self.cfg.record_dir is None:
            return
        out = Path(self.cfg.record_dir)
        for role in ("planner", "worker", "verifier", "judge", "merger"):
            try:
                rec.save_scenarios(out / f"{mission_id[:8]}_{role}.yaml", role=role)
            except Exception:  # noqa: BLE001 — recording must never fail a mission
                log.exception("failed to save %s recording", role)
        log.info("recorded scenarios for mission %s → %s", mission_id, out)

    # ── helpers ───────────────────────────────────────────────────────────
    def _persist_plan(self, mission_id: str, plan) -> list[str]:
        task_dicts = [
            {"id": s.id, "title": s.title, "instructions": s.instructions,
             "acceptance_criteria": s.acceptance_criteria, "depends_on": s.depends_on,
             "files_touched": s.files_touched}
            for s in plan.subtasks
        ]
        self.store.create_tasks(mission_id, task_dicts)
        return [t["id"] for t in task_dicts]

    def _mission_dir(self, mission_id: str) -> Path:
        d = self.cfg.db_path.parent / "missions" / mission_id
        d.mkdir(parents=True, exist_ok=True)
        return d


def rehydrate_pending_missions(store, bus, runner: MissionRunner) -> list[asyncio.Task]:
    """On startup, resume non-terminal missions (RUNNING tasks reset to READY)."""
    tasks: list[asyncio.Task] = []
    for mission in store.non_terminal_missions():
        mid = mission["id"]
        for t in store.get_tasks(mid):
            if t["status"] in ("claimed", "running", "retrying"):
                store.update_task(mid, t["id"], status="ready")
        log.info("resuming mission %s (was %s)", mid, mission["status"])
        tasks.append(asyncio.create_task(runner.run_mission(mid)))
    return tasks
