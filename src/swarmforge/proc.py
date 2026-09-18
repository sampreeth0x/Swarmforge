"""Windows-safe subprocess runner shared by sandbox backends and agent tools."""

from __future__ import annotations

import os
import signal
import subprocess
import time


def run_cmd(argv: list[str], *, cwd: str | None = None, timeout_s: float = 600,
            env: dict | None = None, input_text: str | None = None) -> tuple[int, str, str]:
    """Run a command; never shell=True; UTF-8 tolerant; kills the process tree on timeout."""
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]

    merged_env = None
    if env is not None:
        merged_env = {**os.environ, **env}

    try:
        proc = subprocess.Popen(
            argv,
            cwd=cwd,
            env=merged_env,
            stdin=subprocess.PIPE if input_text is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creationflags,
        )
    except FileNotFoundError:
        return 127, "", f"command not found: {argv[0]}"

    try:
        out, err = proc.communicate(input=input_text, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        out, err = proc.communicate()
        return proc.returncode or 124, out, err + f"\n[swarmforge] timed out after {timeout_s}s"

    decode = lambda b: b.decode("utf-8", errors="replace")  # noqa: E731  (cp1252 junk tolerance)
    return proc.returncode, decode(out), decode(err)


def _kill_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                       capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)  # type: ignore[attr-defined]
        except (ProcessLookupError, PermissionError):
            proc.kill()


def git_argv(repo_cwd: str, *args: str) -> list[str]:
    """Git invocation with Windows-safe settings (autocrlf corrupts diffs)."""
    return ["git", "-C", repo_cwd, "-c", "core.autocrlf=false", "-c", "core.longpaths=true", *args]


def timed(fn, *args, **kwargs):  # noqa: ANN002, ANN003 — small helper for duration tracking
    start = time.monotonic()
    result = fn(*args, **kwargs)
    return result, time.monotonic() - start
