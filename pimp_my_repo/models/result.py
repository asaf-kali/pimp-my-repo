from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class BoostResult(BaseModel):
    name: str
    status: Literal["applied", "skipped", "failed"]
    message: str


class RunResult(BaseModel):
    repo_path: str
    branch_name: str
    started_at: datetime = Field(default_factory=datetime.now)
    boosts: list[BoostResult] = Field(default_factory=list)
