"""Utility for creating mock git repositories in tests."""

import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator


class RepositoryController:
    """A controller for a mock git repository for testing purposes."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def _run_git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        """Run a git command in the repository directory."""
        cmd = ["git", *args]
        return subprocess.run(  # noqa: S603
            cmd,
            cwd=self.path,
            check=check,
            capture_output=True,
            text=True,
        )

    def add_file(self, relative_path: str, content: str) -> Path:
        """Add a file to the repository."""
        full_path = self.path / relative_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)
        return full_path

    def add_and_commit(self, relative_path: str, content: str, message: str = "Add file") -> None:
        """Add a file and commit it."""
        self.add_file(relative_path, content)
        self._run_git("add", relative_path)
        self._run_git("commit", "-m", message)

    def commit_all(self, message: str = "Commit changes") -> None:
        """Stage and commit all changes."""
        self._run_git("add", "-A")
        self._run_git("commit", "-m", message)

    def create_branch(self, branch_name: str) -> None:
        """Create and switch to a new branch."""
        result = self._run_git("branch", "--list", branch_name, check=False)
        if result.stdout.strip():
            self._run_git("checkout", branch_name)
        else:
            self._run_git("checkout", "-b", branch_name)

    def is_clean(self) -> bool:
        """Check if git working directory is clean."""
        result = self._run_git("status", "--porcelain", check=False)
        return result.returncode == 0 and not result.stdout.strip()

    def commit_count(self) -> int:
        """Return the number of commits on HEAD."""
        result = self._run_git("rev-list", "--count", "HEAD")
        return int(result.stdout.strip())


@pytest.fixture
def mock_repo() -> Generator[RepositoryController]:
    """Create a temporary directory with an initialized git repository."""
    tmp_dir = TemporaryDirectory()
    tmp_path = Path(tmp_dir.name)

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)  # noqa: S607
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],  # noqa: S607
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],  # noqa: S607
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    repo = RepositoryController(tmp_path)
    repo.add_and_commit(relative_path="README.md", content="# Test", message="Initial commit")
    yield repo
    tmp_dir.cleanup()
