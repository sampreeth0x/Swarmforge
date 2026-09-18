"""SwarmForge configuration — env-driven via pydantic-settings."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SWARMFORGE_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # mock | tokenfactory | nim
    mode: str = "mock"

    # ── Nebius Token Factory (OpenAI-compatible) ──────────────────────────
    llm_base_url: str = "https://api.tokenfactory.nebius.com/v1"
    nebius_api_key: str = Field(default="", validation_alias="NEBIUS_TOKEN_FACTORY_API_KEY")

    model_planner: str = "nemotron-3-super-120b-a12b"
    model_worker: str = "nemotron-3-nano-30b-a3b"

    # ── NVIDIA NIM fallback ───────────────────────────────────────────────
    nim_base_url: str = "https://integrate.api.nvidia.com/v1"
    nim_api_key: str = Field(default="", validation_alias="NVIDIA_NIM_API_KEY")

    # ── Sandboxes ─────────────────────────────────────────────────────────
    sandbox_backend: str = "local"  # local | contree
    nebius_project_id: str = Field(default="", validation_alias="NEBIUS_PROJECT_ID")

    # ── Swarm sizing ──────────────────────────────────────────────────────
    workers: int = 4
    agent_max_steps: int = 24

    # ── Server ────────────────────────────────────────────────────────────
    host: str = "127.0.0.1"
    port: int = 8000
    db_path: Path = ROOT_DIR / "data" / "swarmforge.db"
    scenario_dir: Path = ROOT_DIR / "mock" / "scenarios"

    @property
    def llm_api_key(self) -> str:
        return self.nebius_api_key if self.mode == "tokenfactory" else self.nim_api_key

    @property
    def llm_url(self) -> str:
        return self.llm_base_url if self.mode == "tokenfactory" else self.nim_base_url


def load_config() -> Config:
    return Config()
