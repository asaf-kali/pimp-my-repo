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

    @classmethod
    def get_name(cls) -> str:
        """Extract boost name from class name.

        Returns:
            Boost name (e.g., 'UvBoost' -> 'uv')

        """
        class_name = cls.__name__.lower()
        # Remove 'boost' suffix
        if class_name.endswith("boost"):
            return class_name[:-5]
        return class_name

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
