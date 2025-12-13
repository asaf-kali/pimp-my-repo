"""Base boost interface."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


class Boost(ABC):
    """Abstract base class for all boosts."""

    def __init__(self, repo_path: Path) -> None:
        """Initialize boost with repository path."""
        self.repo_path = repo_path

    @abstractmethod
    def check_preconditions(self) -> bool:
        """Verify prerequisites for applying this boost."""
        raise NotImplementedError

    @abstractmethod
    def apply(self) -> None:
        """Perform the migration/configuration."""
        raise NotImplementedError

    @abstractmethod
    def verify(self) -> bool:
        """Run the tool and ensure it works correctly."""
        raise NotImplementedError

    @abstractmethod
    def commit_message(self) -> str:
        """Generate commit message for this boost."""
        raise NotImplementedError
