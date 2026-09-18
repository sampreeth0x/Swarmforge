"""API request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class MissionCreate(BaseModel):
    request: str = Field(min_length=1, max_length=4000, description="The feature request")
    workers: int = Field(default=4, ge=2, le=8)


class MissionOut(BaseModel):
    id: str
    request: str
    status: str
    workers: int
    result_branch: str | None = None
    error: str | None = None
