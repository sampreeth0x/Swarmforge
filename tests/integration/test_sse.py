"""SSE stream test over a real in-process uvicorn server.

httpx's ASGITransport buffers whole responses, so streaming endpoints must be
tested over TCP. uvicorn serves on an ephemeral port in the same event loop.
"""

from __future__ import annotations

import asyncio
import json
import socket

import httpx
import pytest_asyncio
import uvicorn

from swarmforge.api.app import create_app
from swarmforge.config import ROOT_DIR, Config


@pytest_asyncio.fixture()
async def server_url(config):
    app = create_app(config)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    port = sock.getsockname()[1]
    uv_cfg = uvicorn.Config(app, log_level="warning", lifespan="on")
    server = uvicorn.Server(uv_cfg)
    task = asyncio.create_task(server.serve(sockets=[sock]))
    for _ in range(100):
        if server.started:
            break
        await asyncio.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    await task


async def test_sse_replays_events(server_url: str) -> None:
    async with httpx.AsyncClient(base_url=server_url, timeout=10) as client:
        r = await client.post("/api/missions", json={"request": "add dark mode", "workers": 3})
        mid = r.json()["id"]

        # A second mission's events must not bleed into the first mission's stream
        await client.post("/api/missions", json={"request": "second", "workers": 2})

        async with client.stream("GET", f"/api/missions/{mid}/events") as resp:
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")
            body = b""
            async for chunk in resp.aiter_bytes():
                body += chunk
                if b"mission.created" in body:
                    break
        assert b"id: 1" in body


@pytest_asyncio.fixture()
async def live_server_url(tmp_path):
    """Like server_url but with the repo's real mock scenarios (mission must succeed)."""
    cfg = Config(db_path=tmp_path / "swarmforge.db",
                 scenario_dir=ROOT_DIR / "mock" / "scenarios")
    app = create_app(cfg)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    port = sock.getsockname()[1]
    uv_cfg = uvicorn.Config(app, log_level="warning", lifespan="on")
    server = uvicorn.Server(uv_cfg)
    task = asyncio.create_task(server.serve(sockets=[sock]))
    for _ in range(100):
        if server.started:
            break
        await asyncio.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    await task


async def test_sse_delivers_events_live(live_server_url: str) -> None:
    """Regression: live frames must arrive while the mission runs, not just on
    replay. bus.publish used to fan out the pre-insert Event copy (id=0), which
    the stream dropped as 'already seen' — the dashboard froze after snapshot."""
    async with httpx.AsyncClient(base_url=live_server_url, timeout=60) as client:
        r = await client.post(
            "/api/missions",
            json={"request": "Add dark mode support to the fixture repo", "workers": 2})
        mid = r.json()["id"]

        seen: list[str] = []
        async with client.stream("GET", f"/api/missions/{mid}/events") as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    seen.append(json.loads(line[6:])["kind"])
                    if seen[-1] in ("mission.done", "mission.failed"):
                        break
        assert seen[-1] == "mission.done"
        assert "verdict" in seen and "merge.done" in seen
