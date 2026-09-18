"""SSE stream test over a real in-process uvicorn server.

httpx's ASGITransport buffers whole responses, so streaming endpoints must be
tested over TCP. uvicorn serves on an ephemeral port in the same event loop.
"""

from __future__ import annotations

import asyncio
import socket

import httpx
import pytest_asyncio
import uvicorn

from swarmforge.api.app import create_app


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
