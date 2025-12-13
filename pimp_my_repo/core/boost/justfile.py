"""Justfile boost implementation."""

from pimp_my_repo.core.boost.base import Boost


class JustfileBoost(Boost):
    """Boost for generating justfile with common commands."""

    def check_preconditions(self) -> bool:
        """Verify prerequisites for applying justfile boost."""
        raise NotImplementedError

    def apply(self) -> None:
        """Generate justfile with common commands."""
        raise NotImplementedError

    def verify(self) -> bool:
        """Verify justfile is working correctly."""
        raise NotImplementedError

    def commit_message(self) -> str:
        """Generate commit message for justfile boost."""
        return "✨ Add justfile with common commands"
