"""UV boost implementation."""

from pimp_my_repo.core.boost.base import Boost


class UvBoost(Boost):
    """Boost for integrating UV dependency management."""

    def check_preconditions(self) -> bool:
        """Verify prerequisites for applying UV boost."""
        raise NotImplementedError

    def apply(self) -> None:
        """Create pyproject.toml if needed and migrate requirements.txt."""
        raise NotImplementedError

    def verify(self) -> bool:
        """Verify UV is working correctly."""
        raise NotImplementedError

    def commit_message(self) -> str:
        """Generate commit message for UV boost."""
        return "✨ Add UV dependency management"
