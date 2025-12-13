"""Mypy boost implementation."""

from pimp_my_repo.core.boost.base import Boost


class MypyBoost(Boost):
    """Boost for integrating Mypy type checker."""

    def check_preconditions(self) -> bool:
        """Verify prerequisites for applying Mypy boost."""
        raise NotImplementedError

    def apply(self) -> None:
        """Configure Mypy in strict mode in pyproject.toml."""
        raise NotImplementedError

    def verify(self) -> bool:
        """Verify Mypy is working correctly."""
        raise NotImplementedError

    def commit_message(self) -> str:
        """Generate commit message for Mypy boost."""
        return "✨ Add Mypy type checker"
