"""Git operations for pimp-my-repo."""

import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

import logging

log = logging.getLogger(__name__)
_DEFAULT_BRANCH_NAME = "feat/pmr"
COMMIT_AUTHOR = "pmr <pimp-my-repo@pypi.org>"


class GitController:
    """Manages git operations for the repository."""

    def __init__(self, repo_path: Path) -> None:
        """Initialize GitController with repository path."""
        self.repo_path = repo_path

    def init_pmr(self, branch_name: str = _DEFAULT_BRANCH_NAME) -> None:
        """Set up git manager and prepare the pmr branch."""
        log.info("Checking git status...")
        if not self.is_clean():
            msg = "Git working directory is not clean. Please commit or stash your changes."
            raise ValueError(msg)
        log.info("Switching to branch: [%s]", branch_name)
        self.switch_branch(branch_name)
        log.info("On branch: [%s]", branch_name)

    def execute(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        """Run a git command in the repository directory."""
        cmd = ["git", *args]
        return subprocess.run(  # noqa: S603
            cmd,
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=check,
        )

    def add(self, *paths: str) -> None:
        """Stage files for commit."""
        if paths:
            self.execute("add", *paths)
        else:
            self.execute("add", "-A")

    def commit(self, message: str, *, no_verify: bool = True, author: str = COMMIT_AUTHOR) -> bool:
        """Commit changes with the given message.

        Args:
            message: Commit message
            no_verify: Skip git hooks
            author: Author string (defaults to COMMIT_AUTHOR)

        Returns:
            True if a commit was created, False if there was nothing to commit.

        """
        self.execute("add", "-A")
        if self.is_clean():
            return False
        commit_args = ["commit", "--author", author, "-m", message]
        if no_verify:
            commit_args.append("--no-verify")
        self.execute(*commit_args)
        return True

    def status(self, *, porcelain: bool = False) -> subprocess.CompletedProcess[str]:
        """Get git status."""
        args = ["status"]
        if porcelain:
            args.append("--porcelain")
        return self.execute(*args, check=False)

    def reset_tracking(self) -> None:
        """Untrack all files then re-add, so gitignored files leave the index."""
        self.execute("rm", "-r", "--cached", ".")
        self.execute("add", "-A")

    def is_clean(self) -> bool:
        """Check if git working directory is clean."""
        result = self.execute("status", "--porcelain", check=False)
        return result.returncode == 0 and not result.stdout.strip()

    def switch_branch(self, branch_name: str) -> None:
        """Create and switch to a new branch."""
        # Check if branch exists
        result = self.execute("branch", "--list", branch_name, check=False)
        if result.stdout.strip():
            # Branch exists, switch to it
            self.execute("checkout", branch_name)
        else:
            # Create new branch
            self.execute("checkout", "-b", branch_name)

    def get_origin_url(self) -> str:
        """Get the git origin URL."""
        result = self.execute("remote", "get-url", "origin", check=True)
        if not result.stdout.strip():
            msg = "Git origin URL is empty"
            raise ValueError(msg)
        return result.stdout.strip()

    def get_current_commit_sha(self) -> str:
        """Get the current commit SHA."""
        result = self.execute("rev-parse", "HEAD", check=True)
        if not result.stdout.strip():
            msg = "Git commit SHA is empty"
            raise ValueError(msg)
        return result.stdout.strip()

    def reset_hard(self, sha: str) -> None:
        """Reset the working tree and index to the given commit SHA."""
        self.execute("reset", "--hard", sha)
