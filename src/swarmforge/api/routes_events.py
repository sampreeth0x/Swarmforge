"""SSE event stream: GET /api/missions/{id}/events

Snapshot-first: replay stored events after Last-Event-ID, then stream live,
with a heartbeat so proxies keep the connection open.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from swarmforge.events.events import Event

router = APIRouter(prefix="/api/missions", tags=["events"])

HEARTBEAT_SECONDS = 15.0


def _sse(ev: Event) -> str:
    # No `event:` line — named event types don't fire EventSource.onmessage,
    # and the kind is already in the JSON payload.
    return f"id: {ev.id}\ndata: {json.dumps(ev.to_sse_dict())}\n\n"


@router.get("/{mission_id}/events")
async def mission_events(mission_id: str, request: Request) -> StreamingResponse:
    store = request.app.state.store
    bus = request.app.state.bus

    last_id = 0
    if header := request.headers.get("last-event-id"):
        try:
            last_id = int(header)
        except ValueError:
            last_id = 0
    else:
        last_id = int(request.query_params.get("last_event_id", "0"))

    async def stream():
        nonlocal last_id
        live_q = bus.subscribe(mission_id)
        try:
            # Subscribe first, then snapshot — replay covers anything queued meanwhile.
            for ev in store.get_events(mission_id, since_id=last_id):
                yield _sse(ev)
                last_id = max(last_id, ev.id)
            while True:
                try:
                    ev = await asyncio.wait_for(live_q.get(), timeout=HEARTBEAT_SECONDS)
                except TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                if ev.id <= last_id:
                    continue
                last_id = ev.id
                yield _sse(ev)
        finally:
            bus.unsubscribe(live_q, mission_id)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
