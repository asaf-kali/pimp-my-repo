"""UV operations controller for boosts."""

import subprocess
from typing import TYPE_CHECKING

from loguru import logger

from pimp_my_repo.core.boosts.base import BoostSkippedError

if TYPE_CHECKING:
    from pathlib import Path


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

    def add_package(
        self,
        package: str,
        *,
        group: str | None = None,
        dev: bool = False,
    ) -> None:
        """Add a package using uv add, skipping if already present.

        Requires pyproject controller to check if package exists.
        """
        pyproject = self.pyproject
        if pyproject.is_package_in_deps(package):
            logger.info(f"{package} already in dependencies, skipping uv add")
            return

        logger.info(f"Adding {package} dependency...")
        cmd = ["add", "--no-install-project"]
        if dev:
            cmd.append("--dev")
        elif group:
            cmd.extend(["--group", group])
        cmd.append(package)
        self.run(*cmd)

    def verify_present(self) -> None:
        """Verify that uv is installed and available."""
        try:
            result = self.run("--version", check=False)
            if result.returncode != 0:
                msg = "uv is not available"
                raise BoostSkippedError(msg)
        except (FileNotFoundError, OSError) as e:
            msg = "uv is not installed"
            raise BoostSkippedError(msg) from e
