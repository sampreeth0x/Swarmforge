"""LocalWorktreeBackend unit tests against a disposable seeded repo."""

from __future__ import annotations

from pathlib import Path

import pytest

from swarmforge.sandbox.base import SandboxSpec
from swarmforge.sandbox.fixtures import make_repo
from swarmforge.sandbox.local_worktree import LocalWorktreeBackend


@pytest.fixture()
async def backend(tmp_path) -> LocalWorktreeBackend:
    repo = make_repo(tmp_path / "seed")
    return LocalWorktreeBackend(tmp_path / "worktrees", repo)


async def test_create_exec_commit_diff(backend: LocalWorktreeBackend) -> None:
    h = await backend.create(SandboxSpec(), label="w1")
    assert h.backend == "local" and "swarm/" in h.branch

    r = await backend.exec(h, ["python", "-c", "print('hello from sandbox')"])
    assert r.ok and "hello from sandbox" in r.stdout

    await backend.write_file(h, "static/dark.css", "body.dark { background: #111; }")
    sha = await backend.commit(h, "add dark theme")
    assert len(sha) == 40

    diff = await backend.diff(h)
    assert "dark.css" in diff and "+body.dark" in diff

    patch = await backend.export_patch(h, task_id="t1", agent_id="a1")
    assert patch.stats.get("static/dark.css") == 1


async def test_fork_branches_from_parent(backend: LocalWorktreeBackend) -> None:
    parent = await backend.create(SandboxSpec(), label="w2")
    await backend.write_file(parent, "NOTES.md", "forked from here")
    await backend.commit(parent, "checkpoint")

    child = await backend.fork(parent, label="w2-approach-b")
    assert child.parent_id == parent.id and child.branch != parent.branch

    content = await backend.read_file(child, "NOTES.md")
    assert content == "forked from here"

    # Writes are isolated between fork siblings
    await backend.write_file(child, "ONLY_CHILD.md", "x")
    files = await backend.list_files(parent)
    assert "ONLY_CHILD.md" not in files
    assert "ONLY_CHILD.md" in await backend.list_files(child)


async def test_teardown(backend: LocalWorktreeBackend) -> None:
    h = await backend.create(SandboxSpec(), label="w3")
    workdir = h.workdir
    await backend.teardown(h)
    assert not Path(workdir).exists()


async def test_path_traversal_guard(backend: LocalWorktreeBackend) -> None:
    h = await backend.create(SandboxSpec(), label="w4")
    with pytest.raises(ValueError):
        await backend.read_file(h, "../../outside.txt")
