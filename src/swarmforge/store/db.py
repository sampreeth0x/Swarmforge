"""SQLite persistence layer (WAL) — missions, tasks, events, candidates, agents."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from dataclasses import replace
from pathlib import Path

from swarmforge.events.events import Event

MIGRATIONS_SQL = """
CREATE TABLE IF NOT EXISTS missions (
    id          TEXT PRIMARY KEY,
    request     TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'planning',
    workers     INTEGER NOT NULL DEFAULT 4,
    result_branch TEXT,
    error       TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
    mission_id  TEXT NOT NULL REFERENCES missions(id),
    id          TEXT NOT NULL,
    seq         INTEGER NOT NULL,
    title       TEXT NOT NULL,
    instructions TEXT NOT NULL,
    acceptance_criteria TEXT NOT NULL DEFAULT '[]',
    depends_on  TEXT NOT NULL DEFAULT '[]',
    files_touched TEXT NOT NULL DEFAULT '[]',
    status      TEXT NOT NULL DEFAULT 'pending',
    assigned_agent TEXT,
    attempts    INTEGER NOT NULL DEFAULT 0,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (mission_id, id)
);
CREATE INDEX IF NOT EXISTS idx_tasks_mission ON tasks(mission_id, status);
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    mission_id  TEXT NOT NULL,
    agent_id    TEXT,
    kind        TEXT NOT NULL,
    payload     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_mission ON events(mission_id, id);
CREATE TABLE IF NOT EXISTS candidates (
    id          TEXT PRIMARY KEY,
    mission_id  TEXT NOT NULL,
    task_id     TEXT NOT NULL,
    agent_id    TEXT NOT NULL,
    diff        TEXT NOT NULL,
    commit_message TEXT NOT NULL DEFAULT '',
    stats       TEXT NOT NULL DEFAULT '{}',
    tests_passed INTEGER NOT NULL DEFAULT 0,
    test_output TEXT NOT NULL DEFAULT '',
    verdict     TEXT,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_candidates_mission ON candidates(mission_id);
CREATE TABLE IF NOT EXISTS agents (
    id          TEXT NOT NULL,
    mission_id  TEXT NOT NULL,
    role        TEXT NOT NULL,
    model       TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'idle',
    steps       INTEGER NOT NULL DEFAULT 0,
    prompt_tokens    INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd    REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (mission_id, id)
);
CREATE INDEX IF NOT EXISTS idx_agents_mission ON agents(mission_id);
"""


def _now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


class Store:
    """Thread-safe sqlite DAO. One connection, guarded by a lock (sync, fast)."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock, self._conn as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.executescript(MIGRATIONS_SQL)

    # ── helpers ───────────────────────────────────────────────────────────
    def _exec(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock, self._conn as c:
            return c.execute(sql, params)

    def _rows(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock, self._conn as c:
            return list(c.execute(sql, params).fetchall())

    # ── missions ──────────────────────────────────────────────────────────
    def create_mission(self, request: str, workers: int) -> str:
        mid = uuid.uuid4().hex[:12]
        self._exec(
            "INSERT INTO missions (id, request, status, workers, created_at, updated_at)"
            " VALUES (?, ?, 'planning', ?, ?, ?)",
            (mid, request, workers, _now(), _now()),
        )
        return mid

    def get_mission(self, mission_id: str) -> dict | None:
        rows = self._rows("SELECT * FROM missions WHERE id = ?", (mission_id,))
        return dict(rows[0]) if rows else None

    def list_missions(self, limit: int = 50) -> list[dict]:
        return [dict(r) for r in self._rows(
            "SELECT * FROM missions ORDER BY created_at DESC LIMIT ?", (limit,))]

    def update_mission(self, mission_id: str, **fields) -> None:
        allowed = {"status", "result_branch", "error"}
        sets, params = [], []
        for k, v in fields.items():
            if k not in allowed or v is None:
                continue
            sets.append(f"{k} = ?")
            params.append(v)
        sets.append("updated_at = ?")
        params.extend([_now(), mission_id])
        self._exec(f"UPDATE missions SET {', '.join(sets)} WHERE id = ?", tuple(params))

    def non_terminal_missions(self) -> list[dict]:
        return [dict(r) for r in self._rows(
            "SELECT * FROM missions WHERE status NOT IN ('done', 'failed')")]

    # ── events ────────────────────────────────────────────────────────────
    def insert_event(self, ev: Event) -> Event:
        with self._lock, self._conn as c:
            cur = c.execute(
                "INSERT INTO events (ts, mission_id, agent_id, kind, payload) VALUES (?, ?, ?, ?, ?)",
                (ev.ts.isoformat(), ev.mission_id, ev.agent_id, str(ev.kind), json.dumps(ev.payload)),
            )
            ev = replace(ev, id=cur.lastrowid)
        return ev

    def get_events(self, mission_id: str, since_id: int = 0) -> list[Event]:
        rows = self._rows(
            "SELECT * FROM events WHERE mission_id = ? AND id > ? ORDER BY id", (mission_id, since_id))
        return [
            Event(
                id=r["id"], ts=_from_iso(r["ts"]), mission_id=r["mission_id"],
                agent_id=r["agent_id"], kind=r["kind"], payload=json.loads(r["payload"]),
            )
            for r in rows
        ]

    # ── tasks ─────────────────────────────────────────────────────────────
    def create_tasks(self, mission_id: str, tasks: list[dict]) -> None:
        with self._lock, self._conn as c:
            for i, t in enumerate(tasks):
                c.execute(
                    "INSERT INTO tasks (id, mission_id, seq, title, instructions,"
                    " acceptance_criteria, depends_on, files_touched, status, updated_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)",
                    (t["id"], mission_id, i, t["title"], t["instructions"],
                     json.dumps(t.get("acceptance_criteria", [])),
                     json.dumps(t.get("depends_on", [])),
                     json.dumps(t.get("files_touched", [])), _now()),
                )

    def get_tasks(self, mission_id: str) -> list[dict]:
        rows = self._rows("SELECT * FROM tasks WHERE mission_id = ? ORDER BY seq", (mission_id,))
        out = []
        for r in rows:
            d = dict(r)
            for col in ("acceptance_criteria", "depends_on", "files_touched"):
                d[col] = json.loads(d[col])
            out.append(d)
        return out

    def update_task(self, mission_id: str, task_id: str, **fields) -> None:
        allowed = {"status", "assigned_agent", "attempts"}
        sets, params = [], []
        for k, v in fields.items():
            if k not in allowed or v is None:
                continue
            sets.append(f"{k} = ?")
            params.append(v)
        params += [mission_id, task_id]
        self._exec(f"UPDATE tasks SET {', '.join(sets)} WHERE mission_id = ? AND id = ?",
                   tuple(params))

    def claim_ready_task(self, mission_id: str, agent_id: str) -> dict | None:
        """Atomically claim the first READY task whose dependencies are all DONE."""
        with self._lock, self._conn as c:
            for row in c.execute(
                "SELECT * FROM tasks WHERE mission_id = ? AND status = 'ready' ORDER BY seq",
                (mission_id,),
            ).fetchall():
                deps = json.loads(row["depends_on"])
                dep_statuses: dict[str, str] = {}
                if deps:
                    placeholders = ",".join("?" * len(deps))
                    dep_statuses = {
                        r["id"]: r["status"]
                        for r in c.execute(
                            f"SELECT id, status FROM tasks WHERE mission_id = ?"
                            f" AND id IN ({placeholders})",
                            (mission_id, *deps)).fetchall()
                    }
                if all(dep_statuses.get(d) == "done" for d in deps):
                    claimed = dict(row)
                    cur = c.execute(
                        "UPDATE tasks SET status = 'claimed', assigned_agent = ?, attempts = attempts + 1"
                        " WHERE mission_id = ? AND id = ? AND status = 'ready'",
                        (agent_id, mission_id, row["id"]))
                    if cur.rowcount == 1:
                        claimed.update(status="claimed", assigned_agent=agent_id)
                        return claimed
        return None

    def ready_tasks_count(self, mission_id: str) -> int:
        rows = self._rows(
            "SELECT COUNT(*) AS n FROM tasks WHERE mission_id = ? AND status = 'ready'", (mission_id,))
        return rows[0]["n"]

    # ── candidates ────────────────────────────────────────────────────────
    def create_candidate(self, mission_id: str, task_id: str, agent_id: str,
                         diff: str, commit_message: str = "", stats: dict | None = None) -> str:
        cid = uuid.uuid4().hex[:12]
        self._exec(
            "INSERT INTO candidates (id, mission_id, task_id, agent_id, diff, commit_message,"
            " stats, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (cid, mission_id, task_id, agent_id, diff, commit_message, json.dumps(stats or {}), _now()),
        )
        return cid

    def update_candidate(self, candidate_id: str, **fields) -> None:
        allowed = {"tests_passed", "test_output", "verdict", "diff"}
        sets, params = [], []
        for k, v in fields.items():
            if k not in allowed or v is None:
                continue
            sets.append(f"{k} = ?")
            params.append(int(v) if isinstance(v, bool) else json.dumps(v) if k == "verdict" else v)
        params.append(candidate_id)
        self._exec(f"UPDATE candidates SET {', '.join(sets)} WHERE id = ?", tuple(params))

    def get_candidate(self, candidate_id: str) -> dict | None:
        rows = self._rows("SELECT * FROM candidates WHERE id = ?", (candidate_id,))
        return _candidate_dict(rows[0]) if rows else None

    def get_candidates(self, mission_id: str) -> list[dict]:
        rows = self._rows(
            "SELECT * FROM candidates WHERE mission_id = ? ORDER BY created_at", (mission_id,))
        return [_candidate_dict(r) for r in rows]

    # ── agents / usage ────────────────────────────────────────────────────
    def upsert_agent(self, agent_id: str, mission_id: str, role: str, model: str) -> None:
        self._exec(
            "INSERT OR IGNORE INTO agents (id, mission_id, role, model) VALUES (?, ?, ?, ?)",
            (agent_id, mission_id, role, model),
        )

    def update_agent(self, mission_id: str, agent_id: str, **fields) -> None:
        allowed = {"status", "steps", "prompt_tokens", "completion_tokens", "cost_usd"}
        sets, params = [], []
        for k, v in fields.items():
            if k not in allowed or v is None:
                continue
            sets.append(f"{k} = ?")
            params.append(v)
        params += [mission_id, agent_id]
        self._exec(f"UPDATE agents SET {', '.join(sets)} WHERE mission_id = ? AND id = ?", tuple(params))

    def get_agents(self, mission_id: str) -> list[dict]:
        return [dict(r) for r in self._rows("SELECT * FROM agents WHERE mission_id = ?", (mission_id,))]

    def add_usage(self, mission_id: str, agent_id: str, prompt_tokens: int, completion_tokens: int,
                  cost_usd: float, steps: int = 1) -> None:
        self._exec(
            "UPDATE agents SET prompt_tokens = prompt_tokens + ?, completion_tokens ="
            " completion_tokens + ?, cost_usd = cost_usd + ?, steps = steps + ?"
            " WHERE mission_id = ? AND id = ?",
            (prompt_tokens, completion_tokens, cost_usd, steps, mission_id, agent_id),
        )


def _from_iso(s: str):
    from datetime import datetime

    return datetime.fromisoformat(s)


def _candidate_dict(r) -> dict:
    d = dict(r)
    d["tests_passed"] = bool(d["tests_passed"])
    d["stats"] = json.loads(d["stats"])
    d["verdict"] = json.loads(d["verdict"]) if d["verdict"] else None
    return d
