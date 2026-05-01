"""UV operations controller for boosts."""

import subprocess
import tempfile
from pathlib import Path

from loguru import logger

from pimp_my_repo.core.tools.subprocess import CommandResult, run_command

# Requirements file line prefixes that reference other files — uv resolves these at parse time,
# which causes packages from an already-processed (or deleted) file to land in the wrong group.
_REQUIREMENTS_INCLUDE_PREFIXES = ("-r ", "--requirement ", "-c ", "--constraint ")


class UvNotFoundError(Exception):
    """Raised when UV is not found and cannot be installed."""


class UvController:
    """Controller for UV operations in boosts."""

    def __init__(self, repo_path: Path) -> None:
        """Initialize UvController with repository path."""
        self.repo_path = repo_path

    def exec(self, *args: str, check: bool = True, log_on_error: bool = True) -> CommandResult:
        """Run a uv command in the repository directory."""
        return run_command(["uv", *args], cwd=self.repo_path, check=check, log_on_error=log_on_error)

    def exec_uvx(self, *args: str, check: bool = True, log_on_error: bool = True) -> CommandResult:
        """Run a uvx command in the repository directory."""
        return run_command(["uvx", *args], cwd=self.repo_path, check=check, log_on_error=log_on_error)

    def verify_present(self) -> None:
        try:
            result = self.exec("--version", check=False)
            if result.returncode != 0:
                msg = "uv is not available"
                raise UvNotFoundError(msg)
        except (subprocess.CalledProcessError, OSError) as e:
            msg = f"uv is not available: {e}"
            raise UvNotFoundError(msg) from e

    def sync_all(self) -> None:
        """Sync all dependency groups and extras."""
        logger.info("Running uv sync --all-groups --all-extras...")
        self.exec("sync", "--all-groups", "--all-extras")

    def sync_group(self, group: str) -> None:
        """Sync a specific dependency group (additive — does not remove other installed packages)."""
        logger.debug(f"Syncing dependency group: [{group}]...")
        self.exec("sync", "--group", group, "--inexact")

    def add_package(
        self,
        package: str,
        *,
        group: str | None = None,
    ) -> None:
        """Add a package using uv add."""
        logger.info(f"Adding [{package}] dependency...")
        cmd = ["add", "--no-sync"]
        if group:
            cmd.extend(["--group", group])
        cmd.append(package)
        self.exec(*cmd)

    def add_from_requirements_file(
        self,
        requirements_file: Path,
        *,
        group: str | None = None,
    ) -> None:
        """Add dependencies from a requirements file using uv add -r.

        Include directives (-r, -c) are stripped before passing the file to uv so that
        cross-file references (e.g. ``-r requirements.txt`` inside requirements-dev.txt)
        don't pull packages into the wrong dependency group.
        """
        logger.info(f"Adding dependencies from [{requirements_file.name}]...")
        lines = requirements_file.read_text().splitlines(keepends=True)
        filtered = [line for line in lines if not line.lstrip().startswith(_REQUIREMENTS_INCLUDE_PREFIXES)]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
            tmp.writelines(filtered)
            tmp_path = Path(tmp.name)
        try:
            cmd = ["add", "--no-sync", "-r", str(tmp_path)]
            if group:
                cmd.extend(["--group", group])
            self.exec(*cmd)
        finally:
            tmp_path.unlink()
