from enum import StrEnum

from pydantic import BaseModel


class BoostResultStatus(StrEnum):
    APPLIED = "applied"
    SKIPPED = "skipped"
    FAILED = "failed"


class BoostResult(BaseModel):
    name: str
    status: BoostResultStatus
    message: str
