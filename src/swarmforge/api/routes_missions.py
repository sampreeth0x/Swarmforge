"""Mission REST routes."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request

from swarmforge.api.schemas import MissionCreate, MissionOut

router = APIRouter(prefix="/api/missions", tags=["missions"])


def _ctx(request: Request):
    return request.app.state.store, request.app.state.bus


@router.post("", response_model=MissionOut, status_code=201)
async def create_mission(body: MissionCreate, request: Request) -> MissionOut:
    store, bus = _ctx(request)
    mid = store.create_mission(body.request, body.workers)
    # mission.created is published by the orchestrator so CLI missions emit it too.
    runner = getattr(request.app.state, "run_mission", None)
    if runner is not None:
        asyncio.create_task(runner(mid))
    mission = store.get_mission(mid)
    assert mission is not None
    return MissionOut(**{k: mission[k] for k in MissionOut.model_fields})


@router.get("")
async def list_missions(request: Request) -> list[dict]:
    store, _ = _ctx(request)
    return store.list_missions()


@router.get("/{mission_id}")
async def get_mission(mission_id: str, request: Request) -> dict:
    store, _ = _ctx(request)
    mission = store.get_mission(mission_id)
    if mission is None:
        raise HTTPException(404, "mission not found")
    out = dict(mission)
    out["tasks"] = store.get_tasks(mission_id)
    out["agents"] = store.get_agents(mission_id)
    out["candidates"] = store.get_candidates(mission_id)
    return out
