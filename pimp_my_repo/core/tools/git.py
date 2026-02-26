"""Git operations for pimp-my-repo."""

import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

COMMIT_AUTHOR = "pmr <pimp-my-repo@pypi.org>"


class GitController:
    """Manages git operations for the repository."""

    def __init__(self, repo_path: Path) -> None:
        """Initialize GitController with repository path."""
        self.repo_path = repo_path

    def _run_git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        """Run a git command in the repository directory."""
        cmd = ["git", *args]
        return subprocess.run(  # noqa: S603
            cmd,
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=check,
        )

    def run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        """Run a git command in the repository directory."""
        return self._run_git(*args, check=check)

    def add(self, *paths: str) -> None:
        """Stage files for commit."""
        if paths:
            self._run_git("add", *paths)
        else:
            self._run_git("add", "-A")

    def commit(self, message: str, *, no_verify: bool = True, author: str = COMMIT_AUTHOR) -> bool:
        """Commit changes with the given message.

        Args:
            message: Commit message
            no_verify: Skip git hooks
            author: Author string (defaults to COMMIT_AUTHOR)

        Returns:
            True if a commit was created, False if there was nothing to commit.

        """
        self._run_git("add", "-A")
        if self.is_clean():
            return False
        commit_args = ["commit", "--author", author, "-m", message]
        if no_verify:
            commit_args.append("--no-verify")
        self._run_git(*commit_args)
        return True

    def status(self, *, porcelain: bool = False) -> subprocess.CompletedProcess[str]:
        """Get git status."""
        args = ["status"]
        if porcelain:
            args.append("--porcelain")
        return self._run_git(*args, check=False)

    def reset_tracking(self) -> None:
        """Untrack all files then re-add, so gitignored files leave the index."""
        self._run_git("rm", "-r", "--cached", ".")
        self._run_git("add", "-A")

    def is_clean(self) -> bool:
        """Check if git working directory is clean."""
        result = self._run_git("status", "--porcelain", check=False)
        return result.returncode == 0 and not result.stdout.strip()

    def create_branch(self, branch_name: str) -> None:
        """Create and switch to a new branch."""
        # Check if branch exists
        result = self._run_git("branch", "--list", branch_name, check=False)
        if result.stdout.strip():
            # Branch exists, switch to it
            self._run_git("checkout", branch_name)
        else:
            # Create new branch
            self._run_git("checkout", "-b", branch_name)

    def get_origin_url(self) -> str:
        """Get the git origin URL."""
        result = self._run_git("remote", "get-url", "origin", check=True)
        if not result.stdout.strip():
            msg = "Git origin URL is empty"
            raise ValueError(msg)
        return result.stdout.strip()

    def get_current_commit_sha(self) -> str:
        """Get the current commit SHA."""
        result = self._run_git("rev-parse", "HEAD", check=True)
        if not result.stdout.strip():
            msg = "Git commit SHA is empty"
            raise ValueError(msg)
        return result.stdout.strip()

    def reset_hard(self, sha: str) -> None:
        """Reset the working tree and index to the given commit SHA."""
        self._run_git("reset", "--hard", sha)
