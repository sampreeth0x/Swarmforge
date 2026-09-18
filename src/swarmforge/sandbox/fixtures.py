"""Git repo factory — seeds a disposable git repo from a template directory.

The examples/target-repo files are committed as plain files (no nested .git);
this copies them into a fresh repo so tests and missions get a clean main.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from swarmforge.proc import git_argv, run_cmd

DEFAULT_TEMPLATE = Path(__file__).resolve().parents[3] / "examples" / "target-repo"


def make_repo(dest: Path, template: Path | None = None) -> Path:
    """Create a fresh git repo at `dest` seeded from the template; returns repo dir."""
    template = template or DEFAULT_TEMPLATE
    dest = Path(dest)
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    shutil.copytree(template, dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
    run_cmd(git_argv(str(dest), "init", "-b", "main"), timeout_s=60)
    run_cmd(git_argv(str(dest), "add", "-A"), timeout_s=60)
    run_cmd(git_argv(str(dest), "-c", "user.name=swarmforge", "-c", "user.email=swarm@forge.local",
                     "commit", "-m", "seed"), timeout_s=60)
    return dest
