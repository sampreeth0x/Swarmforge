"""Store unit tests: missions, events, tasks, atomic claiming."""

from __future__ import annotations

import threading

import pytest

from swarmforge.events.events import Event, EventKind
from swarmforge.store.db import Store


@pytest.fixture()
def store(tmp_path) -> Store:
    return Store(tmp_path / "test.db")


def test_mission_crud(store: Store) -> None:
    mid = store.create_mission("add dark mode", workers=3)
    m = store.get_mission(mid)
    assert m is not None and m["status"] == "planning" and m["workers"] == 3
    store.update_mission(mid, status="done", result_branch="swarm/abc")
    assert store.get_mission(mid)["result_branch"] == "swarm/abc"
    assert store.get_mission("nope") is None


def test_event_persist_and_replay(store: Store) -> None:
    mid = store.create_mission("x", 2)
    e1 = store.insert_event(Event(kind=EventKind.MISSION_CREATED, mission_id=mid))
    e2 = store.insert_event(Event(kind=EventKind.PLAN_READY, mission_id=mid, payload={"n": 2}))
    assert e1.id > 0 and e2.id == e1.id + 1
    events = store.get_events(mid)
    assert [str(e.kind) for e in events] == ["mission.created", "plan.ready"]
    replayed = store.get_events(mid, since_id=e1.id)
    assert [str(e.kind) for e in replayed] == ["plan.ready"]


def _seed_tasks(store: Store, mid: str, n: int) -> None:
    store.create_tasks(mid, [
        {"id": f"t{i}", "title": f"task {i}", "instructions": "do it"} for i in range(n)
    ])


def test_claim_is_atomic(store: Store) -> None:
    """10 concurrent claims over 10 READY tasks → 10 distinct tasks, no double-claims."""
    mid = store.create_mission("x", 8)
    _seed_tasks(store, mid, 10)
    for i in range(10):
        store.update_task(mid, f"t{i}", status="ready")

    claimed: list[str] = []
    lock = threading.Lock()

    def worker(i: int) -> None:
        got = store.claim_ready_task(mid, f"agent-{i}")
        with lock:
            if got:
                claimed.append(got["id"])

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(claimed) == [f"t{i}" for i in range(10)]
    assert len(set(claimed)) == 10


def test_dependency_wave(store: Store) -> None:
    """A task with unfinished deps must not be claimable even when READY-flagged."""
    mid = store.create_mission("x", 2)
    store.create_tasks(mid, [
        {"id": "t0", "title": "first", "instructions": "i"},
        {"id": "t1", "title": "second", "instructions": "i", "depends_on": ["t0"]},
    ])
    store.update_task(mid, "t0", status="ready")
    store.update_task(mid, "t1", status="ready")

    first = store.claim_ready_task(mid, "a0")
    assert first["id"] == "t0"
    # t1 not claimable until t0 done — simulate by marking t1 ready but t0 claimed
    store.update_task(mid, "t1", status="ready")
    assert store.claim_ready_task(mid, "a1") is None  # t0 is 'claimed', not 'done'
    store.update_task(mid, "t0", status="done")
    got = store.claim_ready_task(mid, "a1")
    assert got is not None and got["id"] == "t1"
