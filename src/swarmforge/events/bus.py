"""EventBus — persist events to the store and fan out to SSE subscribers."""

from __future__ import annotations

import asyncio
from collections import defaultdict

from swarmforge.events.events import Event, EventKind


class EventBus:
    """Every event is persisted (assigning its id) then fanned out to per-client queues."""

    def __init__(self, store) -> None:  # store: swarmforge.store.db.Store (circular import avoided)
        self._store = store
        self._queues: dict[str | None, set[asyncio.Queue[Event]]] = defaultdict(set)

    async def publish(self, kind: EventKind, mission_id: str, payload: dict | None = None,
                      agent_id: str | None = None) -> Event:
        ev = Event(kind=kind, mission_id=mission_id, payload=payload or {}, agent_id=agent_id)
        self._store.insert_event(ev)
        for q in self._queues[None] | self._queues[mission_id]:
            q.put_nowait(ev)
        return ev

    def subscribe(self, mission_id: str | None = None) -> asyncio.Queue[Event]:
        """Live queue. Pass mission_id=None to receive events for all missions."""
        q: asyncio.Queue[Event] = asyncio.Queue()
        self._queues[mission_id].add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[Event], mission_id: str | None = None) -> None:
        self._queues[mission_id].discard(q)
