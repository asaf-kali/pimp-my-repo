"""Justfile boost implementation."""

from pimp_my_repo.core.boost.base import Boost, BoostSkippedError


class JustfileBoost(Boost):
    """Boost for generating justfile with common commands."""

    def apply(self) -> None:
        """Generate justfile with common commands."""
        msg = "Not implemented"
        raise BoostSkippedError(msg)

    def commit_message(self) -> str:
        """Generate commit message for justfile boost."""
        return "✨ Add justfile with common commands"
