"""Merged-result diff: GET /api/missions/{id}/diff."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request

from swarmforge.proc import git_argv, run_cmd

router = APIRouter(prefix="/api/missions", tags=["diff"])


@router.get("/{mission_id}/diff")
async def mission_diff(mission_id: str, request: Request) -> dict:
    store = request.app.state.store
    runner = getattr(request.app.state, "runner", None)
    mission = store.get_mission(mission_id)
    if mission is None:
        raise HTTPException(404, "mission not found")
    branch = mission["result_branch"]
    if not branch or runner is None or runner.repo_dir is None:
        return {"diff": "", "branch": branch or ""}

    code, out, err = await asyncio.to_thread(
        run_cmd, git_argv(str(runner.repo_dir), "diff", f"main...{branch}"), timeout_s=60)
    if code != 0:
        raise HTTPException(500, f"diff failed: {err[:300]}")
    return {"diff": out, "branch": branch}
