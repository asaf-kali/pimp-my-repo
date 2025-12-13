"""State models for pimp-my-repo."""

from datetime import datetime

from pydantic import BaseModel, Field


class BoostState(BaseModel):
    """State for a single boost."""

    name: str
    applied_at: datetime | None = None
    verified_at: datetime | None = None
    commit_sha: str | None = None

    @property
    def applied(self) -> bool:
        """Whether the boost has been applied."""
        return self.applied_at is not None

    @property
    def verified(self) -> bool:
        """Whether the boost has been verified."""
        return self.verified_at is not None


class ProjectState(BaseModel):
    """Overall state for a project."""

    project_key: str = Field(..., description="Unique identifier for the project (git origin URL)")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    repo_path: str
    branch_name: str = "pmr"
    boosts: dict[str, BoostState] = Field(default_factory=dict)
