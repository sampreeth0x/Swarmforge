"""API CRUD integration tests via ASGI transport (no streaming — see test_sse.py)."""

from __future__ import annotations

import httpx

from swarmforge.api.app import create_app


async def test_mission_crud(config) -> None:
    app = create_app(config)
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://t") as client,
    ):
            r = await client.get("/api/health")
            assert r.status_code == 200 and r.json()["ok"] is True

            r = await client.post("/api/missions", json={"request": "add dark mode", "workers": 3})
            assert r.status_code == 201
            mid = r.json()["id"]
            assert r.json()["status"] == "planning"

            r = await client.get(f"/api/missions/{mid}")
            assert r.json()["id"] == mid
            r = await client.get("/api/missions")
            assert len(r.json()) >= 1

            r = await client.get("/api/missions/does-not-exist")
            assert r.status_code == 404
