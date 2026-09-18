"""End-to-end smoke test: boot the server, run a mock mission, wait for merge.

Usage:  uv run python scripts/e2e_mock.py
Exits 0 when the mission reaches status=done with a result branch,
1 on failure/timeout. CI runs this on every push.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

PORT = int(os.environ.get("SWARMFORGE_PORT", "8123"))
BASE = f"http://127.0.0.1:{PORT}"
TIMEOUT_S = 240


def _req(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as res:
        return json.loads(res.read())


def main() -> int:
    env = {**os.environ, "SWARMFORGE_PORT": str(PORT), "SWARMFORGE_MODE": "mock"}
    proc = subprocess.Popen(
        [sys.executable, "-m", "swarmforge.cli", "serve"], env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                if _req("GET", "/api/health").get("ok"):
                    break
            except (urllib.error.URLError, ConnectionError, OSError):
                time.sleep(0.5)
        else:
            print("FAIL: server did not come up", file=sys.stderr)
            return 1

        mission = _req("POST", "/api/missions",
                       {"request": "Add dark mode support to the fixture repo", "workers": 2})
        mid = mission["id"]
        print(f"mission {mid} launched; waiting for merge (<={TIMEOUT_S}s)...")

        deadline = time.time() + TIMEOUT_S
        while time.time() < deadline:
            m = _req("GET", f"/api/missions/{mid}")
            if m["status"] in ("done", "failed"):
                break
            time.sleep(1.5)
        else:
            print(f"FAIL: mission {mid} timed out", file=sys.stderr)
            return 1

        if m["status"] != "done" or not m.get("result_branch"):
            print(f"FAIL: mission {mid} status={m['status']} error={m.get('error')}",
                  file=sys.stderr)
            return 1

        diff = _req("GET", f"/api/missions/{mid}/diff")
        print(f"OK: mission {mid} done -> {m['result_branch']} "
              f"({len(diff['diff'])} diff bytes, {len(m['candidates'])} candidates)")
        return 0
    finally:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True)
        else:
            proc.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
