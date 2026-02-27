"""Utility for creating mock git repositories in tests."""

from typing import TYPE_CHECKING

from pimp_my_repo.core.tools.git import GitController

if TYPE_CHECKING:
    from pathlib import Path


class RepositoryController:
    """A controller for a mock git repository for testing purposes."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._git = GitController(repo_path=path)

    def add_file(self, relative_path: str, content: str) -> Path:
        """Write a file into the repository (does not stage or commit)."""
        full_path = self.path / relative_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)
        return full_path

    def add_and_commit(self, relative_path: str, content: str, message: str = "Add file") -> None:
        """Write a file, stage it, and commit."""
        self.add_file(relative_path=relative_path, content=content)
        self._git.execute("add", relative_path)
        self._git.execute("commit", "-m", message)

    def is_clean(self) -> bool:
        """Check if the git working directory is clean."""
        return self._git.is_clean()

    def commit_count(self) -> int:
        """Return the number of commits on HEAD."""
        result = self._git.execute("rev-list", "--count", "HEAD")
        return int(result.stdout.strip())
