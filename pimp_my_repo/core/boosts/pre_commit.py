"""Pre-commit boost implementation."""

from pimp_my_repo.core.boosts.base import Boost, BoostSkippedError


class PreCommitBoost(Boost):
    """Boost for integrating pre-commit hooks."""

    def apply(self) -> None:
        """Create pre-commit config and install hooks."""
        msg = "Not implemented"
        raise BoostSkippedError(msg)

    def commit_message(self) -> str:
        """Generate commit message for pre-commit boost."""
        return "✨ Add pre-commit hooks"
