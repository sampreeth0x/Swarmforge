"""Sandbox abstractions — every agent works inside a SandboxHandle from a backend."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(slots=True)
class SandboxSpec:
    """What a new sandbox is seeded from."""

    source_dir: str | None = None   # path to the seed repo (local backends)
    image: str = "python:3.12-slim"  # OCI image (cloud backends)
    base_ref: str = "main"
    setup_cmd: str | None = None     # e.g. "pip install -r requirements.txt"


@dataclass(slots=True)
class SandboxHandle:
    id: str
    backend: str          # "local" | "contree"
    workdir: str          # host dir (local) or container workdir (cloud)
    label: str = ""
    branch: str = ""      # git branch for local backends
    state_id: str | None = None   # commit sha (local) / state UUID (contree)
    parent_id: str | None = None  # forked-from handle id


@dataclass(slots=True)
class ExecResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_s: float
    state_id: str | None = None

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


@dataclass(slots=True)
class PatchFile:
    task_id: str
    agent_id: str
    diff: str
    stats: dict = field(default_factory=dict)
    commit_message: str = ""


class SandboxBackend(Protocol):
    """Contract every sandbox backend fulfills — local worktrees and Nebius Contree alike."""

    name: str

    async def create(self, spec: SandboxSpec, *, label: str) -> SandboxHandle: ...

    async def exec(self, h: SandboxHandle, cmd: str, *, cwd: str | None = None,
                   timeout_s: int = 600) -> ExecResult: ...

    async def read_file(self, h: SandboxHandle, path: str) -> str: ...

    async def write_file(self, h: SandboxHandle, path: str, content: str) -> None: ...

    async def list_files(self, h: SandboxHandle, path: str = ".") -> list[str]: ...

    async def fork(self, h: SandboxHandle, *, label: str) -> SandboxHandle: ...

    async def commit(self, h: SandboxHandle, message: str) -> str: ...

    async def diff(self, h: SandboxHandle, *, base_ref: str = "main") -> str: ...

    async def export_patch(self, h: SandboxHandle, *, task_id: str, agent_id: str) -> PatchFile: ...

    async def teardown(self, h: SandboxHandle) -> None: ...


def backend_factory(name: str, **kwargs):
    if name == "local":
        from swarmforge.sandbox.local_worktree import LocalWorktreeBackend

        return LocalWorktreeBackend(**kwargs)
    if name == "contree":
        from swarmforge.sandbox.contree_backend import ContreeBackend  # lazy: optional dep

        return ContreeBackend(**kwargs)
    raise ValueError(f"unknown sandbox backend: {name!r} (expected 'local' or 'contree')")
