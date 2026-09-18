"""Isolate live SSE delivery: in-process uvicorn, POST mission, read stream live."""
import asyncio
import json
import socket
import time

import httpx
import uvicorn

from swarmforge.api.app import create_app


async def main() -> None:
    from swarmforge.config import load_config
    cfg = load_config()
    cfg.db_path = __import__("pathlib").Path("data/debug_sse.db")
    if cfg.db_path.exists():
        cfg.db_path.unlink()

    app = create_app(cfg)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="on"))
    task = asyncio.create_task(server.serve(sockets=[sock]))
    while not server.started:
        await asyncio.sleep(0.05)

    t0 = time.time()
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(f"http://127.0.0.1:{port}/api/missions",
                         json={"request": "add dark mode", "workers": 2})
        mid = r.json()["id"]
        print(f"{time.time()-t0:5.2f}s mission {mid}")

        async def listen() -> None:
            async with c.stream("GET", f"http://127.0.0.1:{port}/api/missions/{mid}/events") as resp:
                print(f"{time.time()-t0:5.2f}s connected")
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        d = json.loads(line[6:])
                        print(f"{time.time()-t0:5.2f}s id={d['id']:3d} {d['kind']}")
                        if d["kind"] in ("mission.done", "mission.failed"):
                            return

        await asyncio.wait_for(listen(), timeout=30)
    server.should_exit = True
    await task


asyncio.run(main())

