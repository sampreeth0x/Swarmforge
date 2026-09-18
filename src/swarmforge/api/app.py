"""FastAPI application factory + lifespan wiring."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from swarmforge.api.routes_diff import router as diff_router
from swarmforge.api.routes_events import router as events_router
from swarmforge.api.routes_missions import router as missions_router
from swarmforge.config import Config, load_config
from swarmforge.events.bus import EventBus
from swarmforge.store.db import Store


def _mount_dashboard(app: FastAPI) -> None:
    from pathlib import Path

    dist = Path(__file__).resolve().parents[3] / "apps" / "dashboard" / "dist"
    if dist.is_dir():
        from fastapi.staticfiles import StaticFiles

        app.mount("/", StaticFiles(directory=dist, html=True), name="dashboard")


def create_app(config: Config | None = None) -> FastAPI:
    cfg = config or load_config()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        store = Store(cfg.db_path)
        bus = EventBus(store)
        app.state.store = store
        app.state.bus = bus
        app.state.config = cfg

        from swarmforge.orchestrator.orchestrator import MissionRunner, rehydrate_pending_missions

        runner = MissionRunner(cfg, store, bus)
        app.state.runner = runner
        app.state.run_mission = runner.run_mission
        rehydrate_pending_missions(store, bus, runner)
        yield
        # local backend: prune worktrees left by crashed missions
        if getattr(runner.backend, "name", "") == "local":
            runner.backend.cleanup_all()

    app = FastAPI(title="SwarmForge", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # dev convenience; dashboard is same-origin in prod
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(missions_router)
    app.include_router(events_router)
    app.include_router(diff_router)

    @app.get("/api/health")
    async def health() -> dict:
        return {"ok": True, "mode": cfg.mode}

    _mount_dashboard(app)
    return app


def run_server() -> None:
    cfg = load_config()
    uvicorn.run(create_app(cfg), host=cfg.host, port=cfg.port)
