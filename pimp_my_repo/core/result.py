from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class BoostResultStatus(StrEnum):
    APPLIED = "applied"
    SKIPPED = "skipped"
    FAILED = "failed"


class BoostResult(BaseModel):
    name: str
    status: BoostResultStatus
    message: str


class RunResult(BaseModel):
    repo_path: str
    branch_name: str
    started_at: datetime = Field(default_factory=datetime.now)
    boosts: list[BoostResult] = Field(default_factory=list)
