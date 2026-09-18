"""Local sandbox backend: git worktrees + subprocess. Zero cloud credentials needed."""

from __future__ import annotations

import shlex
import shutil
import sys
import time
import uuid
from pathlib import Path

from swarmforge.proc import git_argv, run_cmd
from swarmforge.sandbox.base import ExecResult, PatchFile, SandboxHandle, SandboxSpec


class LocalWorktreeBackend:
    """Each sandbox = a git worktree of the seed repo on its own branch.

    Forking = a new worktree branching from the current one — the same
    fork-and-explore model Nebius Contree sandboxes give in the cloud.
    """

    name = "local"

    def __init__(self, root_dir: Path, repo_dir: Path | None = None) -> None:
        self.root = Path(root_dir)
        self.repo_dir = repo_dir  # may be assigned later (per-mission seeding)
        self.root.mkdir(parents=True, exist_ok=True)

    def _repo(self) -> Path:
        if self.repo_dir is None:
            raise RuntimeError("LocalWorktreeBackend has no repo_dir assigned")
        return self.repo_dir

    # ── lifecycle ─────────────────────────────────────────────────────────
    async def create(self, spec: SandboxSpec, *, label: str) -> SandboxHandle:
        sid = uuid.uuid4().hex[:8]
        wt = self.root / f"{label.replace('/', '_')}-{sid}"
        branch = f"swarm/{label}-{sid}"
        base = spec.base_ref or "main"
        run_cmd(git_argv(str(self._repo()), "worktree", "add", str(wt.resolve()),
                         "-b", branch, base))
        if spec.setup_cmd:
            run_cmd(shlex.split(spec.setup_cmd), cwd=str(wt), timeout_s=300)
        return SandboxHandle(id=sid, backend=self.name, workdir=str(wt),
                             label=label, branch=branch, state_id=self._head(str(wt)))

    async def fork(self, h: SandboxHandle, *, label: str) -> SandboxHandle:
        cid = uuid.uuid4().hex[:8]
        wt = self.root / f"{label.replace('/', '_')}-{cid}"
        branch = f"swarm/{label}-{cid}"
        run_cmd(git_argv(str(self._repo()), "worktree", "add", str(wt.resolve()),
                         "-b", branch, h.branch or "main"))
        return SandboxHandle(id=cid, backend=self.name, workdir=str(wt),
                             label=label, branch=branch, state_id=self._head(str(wt)),
                             parent_id=h.id)

    async def teardown(self, h: SandboxHandle) -> None:
        run_cmd(git_argv(str(self._repo()), "worktree", "remove", "--force", h.workdir))
        run_cmd(git_argv(str(self._repo()), "branch", "-D", h.branch), timeout_s=30)

    # ── execution ─────────────────────────────────────────────────────────
    async def exec(self, h: SandboxHandle, cmd: str | list[str], *, cwd: str | None = None,
                   timeout_s: int = 600) -> ExecResult:
        argv = cmd if isinstance(cmd, list) else shlex.split(cmd)
        argv = self._remap_interpreter(argv)
        workdir = str(Path(h.workdir) / cwd) if cwd else h.workdir
        start = time.monotonic()
        code, out, err = run_cmd(argv, cwd=workdir, timeout_s=timeout_s)
        return ExecResult(exit_code=code, stdout=out, stderr=err,
                          duration_s=time.monotonic() - start, state_id=self._head(h.workdir))

    # ── filesystem ────────────────────────────────────────────────────────
    async def read_file(self, h: SandboxHandle, path: str) -> str:
        p = self._resolve_in(h.workdir, path)
        return p.read_text(encoding="utf-8", errors="replace")

    async def write_file(self, h: SandboxHandle, path: str, content: str) -> None:
        p = self._resolve_in(h.workdir, path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8", newline="\n")

    async def list_files(self, h: SandboxHandle, path: str = ".") -> list[str]:
        base = self._resolve_in(h.workdir, path)
        if not base.is_dir():
            return []
        return sorted(
            str(p.relative_to(base)).replace("\\", "/")
            for p in base.rglob("*")
            if ".git" not in p.parts
        )

    # ── git ───────────────────────────────────────────────────────────────
    async def commit(self, h: SandboxHandle, message: str) -> str:
        run_cmd(git_argv(h.workdir, "add", "-A"))
        code, _, _ = run_cmd(git_argv(h.workdir, "commit", "-m", message))
        if code != 0:  # nothing to commit is fine — return current head
            return self._head(h.workdir) or ""
        return self._head(h.workdir) or ""

    async def diff(self, h: SandboxHandle, *, base_ref: str = "main") -> str:
        _, out, _ = run_cmd(git_argv(h.workdir, "diff", f"{base_ref}...HEAD"))
        return out

    async def export_patch(self, h: SandboxHandle, *, task_id: str, agent_id: str,
                           base_ref: str = "main") -> PatchFile:
        diff = await self.diff(h, base_ref=base_ref)
        stats: dict[str, int] = {}
        _, numstat, _ = run_cmd(git_argv(h.workdir, "diff", "--numstat", f"{base_ref}...HEAD"))
        for line in numstat.splitlines():
            parts = line.split("\t")
            if len(parts) >= 3 and parts[0].isdigit():
                stats[parts[2]] = int(parts[0])
        _, msg, _ = run_cmd(git_argv(h.workdir, "log", "-1", "--format=%s"))
        return PatchFile(task_id=task_id, agent_id=agent_id, diff=diff,
                         stats=stats, commit_message=msg.strip())

    # ── internals ─────────────────────────────────────────────────────────
    @staticmethod
    def _remap_interpreter(argv: list[str]) -> list[str]:
        """Local sandboxes run on the host, so bare `python` means the interpreter
        swarmforge itself runs under (venv) — not the base interpreter on PATH,
        which lacks the project's dev deps like pytest."""
        if argv and Path(argv[0]).name.lower() in ("python", "python3", "python.exe"):
            return [sys.executable, *argv[1:]]
        return argv

    @staticmethod
    def _resolve_in(workdir: str, path: str) -> Path:
        root = Path(workdir).resolve()
        p = (Path(workdir) / path).resolve()
        p.relative_to(root)  # path-traversal guard
        return p

    def _head(self, workdir: str) -> str | None:
        code, out, _ = run_cmd(git_argv(str(workdir), "rev-parse", "HEAD"), timeout_s=30)
        return out.strip() if code == 0 else None

    def cleanup_all(self) -> None:
        """Remove stray worktrees left by crashed runs."""
        if self.repo_dir and self.repo_dir.is_dir():
            run_cmd(git_argv(str(self._repo()), "worktree", "prune"))
        if self.root.is_dir():
            shutil.rmtree(self.root, ignore_errors=True)
