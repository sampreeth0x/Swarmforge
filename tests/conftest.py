"""Shared fixtures."""

from __future__ import annotations

import pytest_asyncio

from swarmforge.config import Config


@pytest_asyncio.fixture()
async def config(tmp_path) -> Config:
    return Config(db_path=tmp_path / "swarmforge.db", scenario_dir=tmp_path / "scenarios")
