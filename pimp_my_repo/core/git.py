"""Git operations for pimp-my-repo."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


class GitManager:
    """Manages git operations for the repository."""

    def __init__(self, repo_path: Path) -> None:
        """Initialize GitManager with repository path."""
        self.repo_path = repo_path

    def is_clean(self) -> bool:
        """Check if git working directory is clean."""
        raise NotImplementedError

    def create_branch(self, branch_name: str) -> None:
        """Create and switch to a new branch."""
        raise NotImplementedError

    def commit(self, message: str) -> None:
        """Commit changes with the given message."""
        raise NotImplementedError

    def get_origin_url(self) -> str | None:
        """Get the git origin URL."""
        raise NotImplementedError
