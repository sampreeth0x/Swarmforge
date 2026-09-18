"""Verifier — ground-truth test run per candidate (apply patch in a fresh sandbox, run pytest)."""

from __future__ import annotations

import asyncio
import json
import logging

from swarmforge.agents.base import Agent, AgentConfig, AgentRole
from swarmforge.agents.tools.registry import ToolRegistry
from swarmforge.events.bus import EventBus
from swarmforge.events.events import EventKind
from swarmforge.llm.base import LLMProvider
from swarmforge.sandbox.base import SandboxBackend, SandboxSpec
from swarmforge.store.db import Store

log = logging.getLogger(__name__)

PATCH_FILENAME = "_swarmforge_candidate.patch"
VERIFY_TIMEOUT_S = 300


class Verifier:
    def __init__(self, backend: SandboxBackend, llm: LLMProvider, bus: EventBus, store: Store,
                 *, verifier_model: str, base_branch: str = "main") -> None:
        self.backend = backend
        self.llm = llm
        self.bus = bus
        self.store = store
        self.verifier_model = verifier_model
        self.base_branch = base_branch

    async def verify_all(self, mission_id: str, candidates: list[dict]) -> list[dict]:
        sem = asyncio.Semaphore(4)

        async def one(c: dict) -> dict:
            async with sem:
                return await self.verify(mission_id, c)

        return list(await asyncio.gather(*(one(c) for c in candidates)))

    async def verify(self, mission_id: str, candidate: dict) -> dict:
        """Apply the candidate patch in a fresh sandbox and run the repo's test suite."""
        task = next((t for t in self.store.get_tasks(mission_id)
                     if t["id"] == candidate["task_id"]), {})
        h = await self.backend.create(SandboxSpec(base_ref=self.base_branch),
                                      label=f"verify-{candidate['id']}")
        try:
            if not candidate["diff"].strip():
                return await self._finish(mission_id, candidate, passed=False,
                                          output="candidate made no changes (empty diff)")
            await self.backend.write_file(h, PATCH_FILENAME, candidate["diff"])
            apply_r = await self.backend.exec(
                h, ["git", "-c", "core.autocrlf=false", "apply", "--3way", PATCH_FILENAME])
            if not apply_r.ok:
                return await self._finish(mission_id, candidate, passed=False,
                                    output=f"patch apply failed:\n{apply_r.stderr[:1500]}")

            test_r = await self.backend.exec(h, ["python", "-m", "pytest", "tests/", "-q"],
                                             timeout_s=VERIFY_TIMEOUT_S)
            pytest_ok = test_r.ok

            criteria_verdict = await self._agent_criteria_check(
                mission_id, task, candidate, pytest_ok, test_r)
            passed = pytest_ok and criteria_verdict.get("passed", pytest_ok)

            return await self._finish(mission_id, candidate, passed=passed,
                                output=self._combine_outputs(test_r, criteria_verdict))
        except Exception as exc:  # noqa: BLE001
            log.exception("verifier crashed on candidate %s", candidate["id"])
            return await self._finish(mission_id, candidate, passed=False,
                                output=f"verifier error: {exc}")
        finally:
            await self.backend.teardown(h)

    async def _agent_criteria_check(self, mission_id: str, task: dict, candidate: dict,
                                    pytest_ok: bool, test_r) -> dict:
        """The verifier agent checks acceptance criteria against the test evidence."""
        agent = Agent(
            AgentConfig(agent_id=f"verifier-{candidate['id']}", role=AgentRole.VERIFIER,
                        model=self.verifier_model, max_steps=4),
            mission_id, self.llm, ToolRegistry(), self.bus, self.store)
        result = await agent.run(
            "Verify this candidate solution against its acceptance criteria.",
            context={
                "task_title": task.get("title", ""),
                "acceptance_criteria": task.get("acceptance_criteria", []),
                "pytest_exit_code": test_r.exit_code,
                "pytest_output": test_r.stdout[-3000:],
                "candidate_stats": candidate.get("stats", {}),
            })
        try:
            verdict = json.loads(_strip_json(result.final_text))
            if isinstance(verdict, dict):
                return verdict
        except (json.JSONDecodeError, ValueError):
            pass
        return {"passed": pytest_ok, "notes": "verifier output unparseable; fell back to pytest"}

    async def _finish(self, mission_id: str, candidate: dict, *, passed: bool,
                      output: str) -> dict:
        self.store.update_candidate(candidate["id"], tests_passed=passed,
                                    test_output=output[:8000])
        kind = EventKind.TESTS_PASSED if passed else EventKind.TESTS_FAILED
        await self.bus.publish(kind, mission_id,
                               {"candidate_id": candidate["id"], "task_id": candidate["task_id"],
                                "passed": passed, "output": output[:1000]})
        return {**candidate, "tests_passed": passed, "test_output": output[:8000]}

    @staticmethod
    def _combine_outputs(test_r, verdict: dict) -> str:
        body = test_r.stdout[-2500:] or test_r.stderr[-2500:]
        return (f"pytest exit={test_r.exit_code}\n{body}\n"
                f"verifier agent: {json.dumps(verdict)[:1500]}")


def _strip_json(text: str) -> str:
    text = text.strip()
    if "```" in text:
        for chunk in text.split("```"):
            chunk = chunk.strip().removeprefix("json").strip()
            if chunk.startswith("{"):
                return chunk
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if start != -1 and end != -1 else text
