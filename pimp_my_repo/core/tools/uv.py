"""UV operations controller for boosts."""

import subprocess
from typing import TYPE_CHECKING

from loguru import logger

from pimp_my_repo.core.tools.subprocess import CommandResult, run_command

if TYPE_CHECKING:
    from pathlib import Path


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

    def sync_group(self, group: str) -> None:
        """Sync a specific dependency group (additive — does not remove other installed packages)."""
        logger.debug(f"Syncing dependency group: {group}")
        self.exec("sync", "--group", group)

    def add_package(
        self,
        package: str,
        *,
        group: str | None = None,
    ) -> None:
        """Add a package using uv add."""
        logger.info(f"Adding {package} dependency...")
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
        """Add dependencies from a requirements file using uv add -r."""
        logger.info(f"Adding dependencies from {requirements_file.name}...")
        cmd = ["add", "--no-sync", "-r", str(requirements_file)]
        if group:
            cmd.extend(["--group", group])
        self.exec(*cmd)
