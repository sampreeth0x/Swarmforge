"""Nebius Contree (Sandboxes) backend — VM-isolated sandboxes with git-like state.

Talks to the REST API directly ({base}/v1): POST /instances spawns a run,
GET /operations/{id} polls it, POST /files uploads blobs. Every successful run
produces a new state image UUID — that UUID *is* the fork point, which maps
cleanly onto our SandboxHandle.state_id. Merging stays at the git layer (the
API has no merge endpoint), so the merge arena code is identical for both
backends.
"""

from __future__ import annotations

import asyncio
import base64
import io
import shlex
import tarfile
import time
import uuid
from pathlib import Path

import httpx

from swarmforge.sandbox.base import ExecResult, PatchFile, SandboxHandle, SandboxSpec

WORKSPACE = "/workspace"
TERMINAL = {"SUCCESS", "FAILED", "CANCELLED"}


class ContreeError(RuntimeError):
    pass


class ContreeBackend:
    name = "contree"

    def __init__(self, *, base_url: str, iam_token: str, project_id: str,
                 base_image: str = "tag:python:3.12-slim", poll_interval_s: float = 1.0,
                 default_timeout_s: int = 600, transport: httpx.AsyncBaseTransport | None = None) -> None:
        if not iam_token or not project_id:
            raise ContreeError(
                "contree backend needs NEBIUS_IAM_TOKEN and NEBIUS_PROJECT_ID")
        self.base_url = base_url.rstrip("/")
        self.base_image = base_image
        self._poll = poll_interval_s
        self._default_timeout = default_timeout_s
        self._client = httpx.AsyncClient(
            base_url=self.base_url, timeout=httpx.Timeout(120.0, connect=30.0),
            transport=transport,
            headers={"Authorization": f"Bearer {iam_token}", "Project": project_id})

    # ── low-level API ─────────────────────────────────────────────────────
    async def _run(self, *, image: str, command: str, cwd: str | None = None,
                   env: dict[str, str] | None = None, files: dict | None = None,
                   timeout_s: int | None = None) -> tuple[int, str, str, str]:
        """Spawn one run and wait for it. Returns (exit_code, stdout, stderr, result_image)."""
        body: dict = {
            "image": image,
            "command": command,
            "shell": True,
            "timeout": timeout_s or self._default_timeout,
        }
        if cwd:
            body["cwd"] = cwd
        if env:
            body["env"] = env
        if files:
            body["files"] = files
        r = await self._client.post("/v1/instances", json=body)
        if r.status_code != 201:
            raise ContreeError(f"spawn failed ({r.status_code}): {r.text[:300]}")
        op_url = r.headers.get("Location")
        if not op_url:
            raise ContreeError("spawn response missing Location header")

        # Poll until terminal (docs recommend honoring Retry-After).
        while True:
            op = await self._client.get(op_url)
            op.raise_for_status()
            data = op.json()
            status = data.get("status", "")
            if status in TERMINAL:
                break
            retry = op.headers.get("Retry-After")
            delay = float(retry) if retry else self._poll
            await asyncio.sleep(max(delay, 0.2))
        if status != "SUCCESS":
            err = (data.get("error") or {}) if isinstance(data.get("error"), dict) else {}
            raise ContreeError(
                f"operation {status}: {str(err.get('error', data))[:300]}")

        result = (data.get("metadata") or {}).get("result") or {}
        state = result.get("state") or {}
        code = state.get("exit_code", -1)
        stdout = _stream_text(result.get("stdout"))
        stderr = _stream_text(result.get("stderr"))
        return code, stdout, stderr, data.get("result_image_uuid") or ""

    async def _upload(self, content: bytes) -> str:
        r = await self._client.post("/v1/files", content=content,
                                    headers={"Content-Type": "application/octet-stream"})
        if r.status_code != 201:
            raise ContreeError(f"file upload failed ({r.status_code}): {r.text[:300]}")
        return r.json()["uuid"]

    # ── lifecycle ─────────────────────────────────────────────────────────
    async def create(self, spec: SandboxSpec, *, label: str) -> SandboxHandle:
        sid = uuid.uuid4().hex[:8]
        src = Path(spec.source_dir or getattr(self, "repo_source", None) or "")
        if not src.is_dir():
            raise ContreeError("contree backend needs a repo source dir to seed")

        # Seed workspace: tarball the source repo, upload, unpack, commit.
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            for p in sorted(src.rglob("*")):
                if ".git" in p.parts or "__pycache__" in p.parts:
                    continue
                tar.add(str(p), arcname=p.relative_to(src).as_posix())
        file_uuid = await self._upload(buf.getvalue())

        command = (
            f"mkdir -p {WORKSPACE} && tar -xzf /uploads/repo.tar.gz -C {WORKSPACE} "
            f"&& cd {WORKSPACE} && git init -q -b main && git add -A "
            f"&& git -c user.email=swarm@forge -c user.name=swarm commit -qm seed")
        _, _, stderr, state = await self._run(
            image=self.base_image, command=command, timeout_s=300,
            files={"/uploads/repo.tar.gz": {"uuid": file_uuid}})
        if not state:
            raise ContreeError(f"repo seeding failed: {stderr[:300]}")
        return SandboxHandle(id=sid, backend=self.name, workdir=WORKSPACE,
                             label=label, branch="main", state_id=state)

    async def fork(self, h: SandboxHandle, *, label: str) -> SandboxHandle:
        cid = uuid.uuid4().hex[:8]
        return SandboxHandle(id=cid, backend=self.name, workdir=h.workdir,
                             label=label, branch=h.branch, state_id=h.state_id,
                             parent_id=h.id)

    async def teardown(self, h: SandboxHandle) -> None:
        """States are server-side; nothing to destroy locally."""

    # ── execution ─────────────────────────────────────────────────────────
    async def exec(self, h: SandboxHandle, cmd: str | list[str], *, cwd: str | None = None,
                   timeout_s: int = 600) -> ExecResult:
        command = cmd if isinstance(cmd, str) else " ".join(shlex.quote(a) for a in cmd)
        target = f"{h.workdir}/{cwd}" if cwd else h.workdir
        script = f"cd {target} && {command}"
        start = time.monotonic()
        code, out, err, state = await self._run(
            image=h.state_id, command=script, timeout_s=timeout_s)
        if state:
            h.state_id = state
        return ExecResult(exit_code=code, stdout=out, stderr=err,
                          duration_s=time.monotonic() - start, state_id=state or h.state_id)

    # ── filesystem ────────────────────────────────────────────────────────
    async def read_file(self, h: SandboxHandle, path: str) -> str:
        r = await self.exec(h, ["cat", path])
        if r.exit_code != 0:
            raise FileNotFoundError(f"{path}: {r.stderr[:200]}")
        return r.stdout

    async def write_file(self, h: SandboxHandle, path: str, content: str) -> None:
        b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
        r = await self.exec(h, f"echo {b64} | base64 -d > {shlex.quote(path)}")
        if r.exit_code != 0:
            raise ContreeError(f"write_file failed: {r.stderr[:200]}")

    async def list_files(self, h: SandboxHandle, path: str = ".") -> list[str]:
        r = await self.exec(
            h, f"find {shlex.quote(path)} -type f -not -path '*/.git/*'"
               f" -not -path '*/__pycache__/*' | sort")
        return [line for line in r.stdout.splitlines() if line]

    # ── git ───────────────────────────────────────────────────────────────
    async def commit(self, h: SandboxHandle, message: str) -> str:
        await self.exec(h, "git add -A")
        await self.exec(h, ["git", "-c", "user.email=swarm@forge",
                            "-c", "user.name=swarm", "commit", "-qm", message])
        r = await self.exec(h, ["git", "rev-parse", "HEAD"])
        return r.stdout.strip()

    async def diff(self, h: SandboxHandle, *, base_ref: str = "main") -> str:
        r = await self.exec(h, ["git", "diff", f"{base_ref}...HEAD"])
        return r.stdout

    async def export_patch(self, h: SandboxHandle, *, task_id: str, agent_id: str,
                           base_ref: str = "main") -> PatchFile:
        diff = await self.diff(h, base_ref=base_ref)
        stats: dict[str, int] = {}
        r = await self.exec(h, ["git", "diff", "--numstat", f"{base_ref}...HEAD"])
        for line in r.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) >= 3 and parts[0].isdigit():
                stats[parts[2]] = int(parts[0])
        r = await self.exec(h, ["git", "log", "-1", "--format=%s"])
        return PatchFile(task_id=task_id, agent_id=agent_id, diff=diff,
                         stats=stats, commit_message=r.stdout.strip())


def _stream_text(stream: dict | None) -> str:
    """StreamRepr {value, encoding: ascii|base64, truncated} → text."""
    if not stream:
        return ""
    value = stream.get("value") or ""
    if (stream.get("encoding") or "ascii") == "base64":
        return base64.b64decode(value).decode("utf-8", errors="replace")
    return value
