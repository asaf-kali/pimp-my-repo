"""Base boost interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pimp_my_repo.core.tools import BoostTools


class BoostSkippedError(Exception):
    """Raised inside apply() to signal that the boost should be skipped.

    The boost must not have made any changes before raising this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class Boost(ABC):
    """Abstract base class for all boosts."""

    def __init__(self, tools: BoostTools) -> None:
        """Initialize boost with repository path."""
        self.tools = tools

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
    def apply(self) -> None:
        """Apply the boost.

        Raise BoostSkippedError (before making any changes) if the boost cannot
        or should not be applied. Any other exception signals a failure; the
        caller will reset the git state back to before this method was called.
        """
        raise NotImplementedError

    @abstractmethod
    def commit_message(self) -> str:
        """Generate commit message for this boost."""
        raise NotImplementedError
