"""UV operations controller for boosts."""

import subprocess
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from pathlib import Path


class UvNotFoundError(Exception):
    """Raised when UV is not found and cannot be installed."""


class UvController:
    """Controller for UV operations in boosts."""

    def __init__(self, repo_path: Path) -> None:
        """Initialize UvController with repository path."""
        self.repo_path = repo_path

    def run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        """Run a uv command in the repository directory."""
        cmd = ["uv", *args]
        return subprocess.run(  # noqa: S603
            cmd,
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=check,
        )

    def run_uvx(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        """Run a uvx command in the repository directory."""
        cmd = ["uvx", *args]
        return subprocess.run(  # noqa: S603
            cmd,
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=check,
        )

    def verify_present(self) -> None:
        try:
            result = self.run("--version", check=False)
            if result.returncode != 0:
                msg = "uv is not available"
                raise UvNotFoundError(msg)
        except (subprocess.CalledProcessError, OSError) as e:
            msg = f"uv is not available: {e}"
            raise UvNotFoundError(msg) from e

    def add_package(
        self,
        package: str,
        *,
        group: str | None = None,
        dev: bool = False,
    ) -> None:
        """Add a package using uv add."""
        logger.info(f"Adding {package} dependency...")
        cmd = ["add", "--no-install-project"]
        if dev:
            cmd.append("--dev")
        elif group:
            cmd.extend(["--group", group])
        cmd.append(package)
        self.run(*cmd)

    def add_from_requirements_file(
        self,
        requirements_file: Path,
        *,
        group: str | None = None,
    ) -> None:
        """Add dependencies from a requirements file using uv add -r."""
        logger.info(f"Adding dependencies from {requirements_file.name}...")
        cmd = ["add", "--no-install-project", "-r", str(requirements_file)]
        if group:
            cmd.extend(["--group", group])
        self.run(*cmd)
