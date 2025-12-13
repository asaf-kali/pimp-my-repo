"""Ruff boost implementation."""

from pimp_my_repo.core.boost.base import Boost


class RuffBoost(Boost):
    """Boost for integrating Ruff linter and formatter."""

    def check_preconditions(self) -> bool:
        """Verify prerequisites for applying Ruff boost."""
        raise NotImplementedError

    def apply(self) -> None:
        """Configure Ruff with all rules enabled and migrate existing code."""
        raise NotImplementedError

    def verify(self) -> bool:
        """Verify Ruff is working correctly."""
        raise NotImplementedError

    def commit_message(self) -> str:
        """Generate commit message for Ruff boost."""
        return "✨ Add Ruff linter and formatter"
