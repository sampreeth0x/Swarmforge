"""ContreeBackend against a mocked Sandboxes REST API (httpx.MockTransport)."""

from __future__ import annotations

import base64
import json
import uuid

import httpx
import pytest

from swarmforge.sandbox.base import SandboxSpec
from swarmforge.sandbox.contree_backend import ContreeBackend, ContreeError


def make_backend(handler) -> ContreeBackend:
    return ContreeBackend(
        base_url="https://api.test/sandboxes", iam_token="tok", project_id="proj",
        poll_interval_s=0.01, transport=httpx.MockTransport(handler))


def _op_response(status: str, *, stdout: str = "", stderr: str = "",
                 exit_code: int = 0, result_image: str | None = None) -> httpx.Response:
    result = {"state": {"exit_code": exit_code},
              "stdout": {"value": base64.b64encode(stdout.encode()).decode(),
                         "encoding": "base64"},
              "stderr": {"value": base64.b64encode(stderr.encode()).decode(),
                         "encoding": "base64"}}
    return httpx.Response(200, json={
        "status": status,
        "metadata": {"result": result} if status == "SUCCESS" else {},
        "result_image_uuid": result_image,
    })


async def test_create_seeds_repo_and_captures_state() -> None:
    """create() uploads a tarball, spawns the seeding run, keeps the state UUID."""
    uploads: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith("/v1/files"):
            uploads.append(request.content)
            return httpx.Response(201, json={"uuid": str(uuid.uuid4()), "sha256": "x"})
        if request.method == "POST" and request.url.path.endswith("/v1/instances"):
            body = json.loads(request.content)
            assert body["image"].startswith("tag:")
            assert "git init" in body["command"]
            assert "/uploads/repo.tar.gz" in body["files"]
            op = str(uuid.uuid4())
            return httpx.Response(
                201, headers={"Location": f"/v1/operations/{op}"},
                json={"uuid": str(uuid.uuid4())})
        if request.method == "GET" and "/v1/operations/" in request.url.path:
            state = f"state-{uuid.uuid4().hex[:8]}"
            return _op_response("SUCCESS", result_image=state)
        return httpx.Response(404)

    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "app.py").write_text("print('hi')\n")
        b = make_backend(handler)
        h = await b.create(SandboxSpec(source_dir=td), label="w-t1")
        assert h.state_id.startswith("state-")
        assert h.workdir == "/workspace"
        assert uploads and uploads[0][:2] == b"\x1f\x8b"  # gzip magic


async def test_exec_updates_state_and_decodes_output() -> None:
    polls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal polls
        if request.method == "POST" and request.url.path.endswith("/v1/instances"):
            return httpx.Response(
                201, headers={"Location": f"/v1/operations/{uuid.uuid4()}"},
                json={"uuid": str(uuid.uuid4())})
        if request.method == "GET" and "/v1/operations/" in request.url.path:
            polls += 1
            # first poll EXECUTING, then SUCCESS — exercises the polling loop
            status = "EXECUTING" if polls == 1 else "SUCCESS"
            state = "after" if status == "SUCCESS" else None
            return _op_response(status, stdout="hello\n", result_image=state)
        return httpx.Response(404)

    b = make_backend(handler)
    from swarmforge.sandbox.base import SandboxHandle

    h = SandboxHandle(id="h1", backend="contree", workdir="/workspace",
                      label="x", branch="main", state_id="before")
    r = await b.exec(h, ["echo", "hi"])
    assert r.exit_code == 0
    assert "hello" in r.stdout
    assert h.state_id == "after"  # state advanced


async def test_missing_credentials_raise() -> None:
    with pytest.raises(ContreeError):
        ContreeBackend(base_url="https://api.test", iam_token="", project_id="")
