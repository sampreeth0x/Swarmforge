"""Judge — ranks verified candidates and picks winners."""

from __future__ import annotations

import json
import logging

from swarmforge.agents.base import Agent, AgentConfig, AgentRole
from swarmforge.agents.tools.registry import ToolRegistry
from swarmforge.events.bus import EventBus
from swarmforge.events.events import EventKind
from swarmforge.llm.base import LLMProvider
from swarmforge.store.db import Store

log = logging.getLogger(__name__)

DIFF_CHARS_PER_CANDIDATE = 2000


class Judge:
    def __init__(self, llm: LLMProvider, bus: EventBus, store: Store,
                 *, judge_model: str) -> None:
        self.llm = llm
        self.bus = bus
        self.store = store
        self.judge_model = judge_model

    async def judge(self, mission_id: str, candidates: list[dict]) -> list[dict]:
        """Returns the winning candidates (subset of the input)."""
        if not candidates:
            return []
        passing = [c for c in candidates if c.get("tests_passed")]
        if not passing:
            return []
        if len(passing) == 1:
            winner = passing[0]
            self._store_verdict(winner, [{"candidate_id": winner["id"], "winner": True,
                                          "score": 10.0, "rationale": "only passing candidate"}])
            await self.bus.publish(EventKind.VERDICT, mission_id,
                                   {"winners": [winner["id"]], "reason": "single passing candidate"})
            return [winner]

        agent = Agent(
            AgentConfig(agent_id="judge", role=AgentRole.JUDGE, model=self.judge_model,
                        max_steps=4),
            mission_id, self.llm, ToolRegistry(), self.bus, self.store)
        result = await agent.run("Rank these candidates and pick the winner(s).", context={
            "candidates": [
                {"candidate_id": c["id"], "task_id": c["task_id"], "summary": c["commit_message"],
                 "stats": c.get("stats", {}), "tests_passed": c.get("tests_passed"),
                 "diff": (c.get("diff") or "")[:DIFF_CHARS_PER_CANDIDATE],
                 "verifier_notes": (c.get("test_output") or "")[-500:]}
                for c in passing
            ]})

        ranking = self._parse_ranking(result.final_text, passing)
        await self.bus.publish(EventKind.VERDICT, mission_id,
                               {"ranking": ranking["ranking"]})
        for c in passing:
            self._store_verdict(c, ranking["ranking"])

        winner_ids = [r["candidate_id"] for r in ranking["ranking"] if r.get("winner")]
        winners = [c for c in passing if c["id"] in winner_ids] or [passing[0]]
        return winners

    def _parse_ranking(self, text: str, passing: list[dict]) -> dict:
        valid_ids = {c["id"] for c in passing}
        try:
            data = json.loads(_strip_json(text))
            ranking = [r for r in data.get("ranking", []) if isinstance(r, dict)]
            for r in ranking:
                if r.get("candidate_id") not in valid_ids:
                    r["winner"] = False  # hallucinated ids never win
        except (json.JSONDecodeError, ValueError, AttributeError):
            log.warning("judge output unparseable; defaulting to first passing candidate")
            ranking = [{"candidate_id": passing[0]["id"], "winner": True, "score": 5.0,
                        "rationale": "judge output unparseable; default winner"}]
        return {"ranking": ranking}

    def _store_verdict(self, candidate: dict, ranking: list[dict]) -> None:
        self.store.update_candidate(candidate["id"], verdict={"ranking": ranking})


def _strip_json(text: str) -> str:
    text = text.strip()
    if "```" in text:
        for chunk in text.split("```"):
            chunk = chunk.strip().removeprefix("json").strip()
            if chunk.startswith("{"):
                return chunk
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if start != -1 and end != -1 else text
