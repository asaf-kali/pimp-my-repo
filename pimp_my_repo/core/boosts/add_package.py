"""Utilities for adding packages and managing pyproject.toml."""

import re
import subprocess
from typing import TYPE_CHECKING

from loguru import logger
from tomlkit import TOMLDocument, dumps, loads, table

from pimp_my_repo.core.boosts.base import BoostSkippedError

if TYPE_CHECKING:
    from pathlib import Path
    from typing import Any


def run_uv(repo_path: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a uv command in the repository directory."""
    cmd = ["uv", *args]
    return subprocess.run(  # noqa: S603
        cmd,
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=check,
    )


def run_git(repo_path: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a git command in the repository directory."""
    cmd = ["git", *args]
    return subprocess.run(  # noqa: S603
        cmd,
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=check,
    )


def read_pyproject(repo_path: Path) -> TOMLDocument:
    """Read existing pyproject.toml if it exists."""
    pyproject_path = repo_path / "pyproject.toml"
    with pyproject_path.open(encoding="utf-8") as f:
        return loads(f.read())


def write_pyproject(repo_path: Path, data: TOMLDocument) -> None:
    """Write pyproject.toml."""
    pyproject_path = repo_path / "pyproject.toml"
    with pyproject_path.open("w", encoding="utf-8") as f:
        f.write(dumps(data))


def is_package_in_deps(repo_path: Path, package: str) -> bool:
    """Check if a package is already present in any dependency group in pyproject.toml."""
    try:
        data = read_pyproject(repo_path)
    except (OSError, ValueError):  # fmt: skip
        return False
    package_lower = package.lower()
    for deps in data.get("dependency-groups", {}).values():
        for dep in deps:
            if isinstance(dep, str) and re.split(r"[>=<!@\s\[]", dep)[0].lower() == package_lower:
                return True
    for deps in data.get("project", {}).get("optional-dependencies", {}).values():
        for dep in deps:
            if isinstance(dep, str) and re.split(r"[>=<!@\s\[]", dep)[0].lower() == package_lower:
                return True
    return False


def add_package_to_deps(repo_path: Path, group: str, package: str) -> None:
    """Add a package to a dependency group directly in pyproject.toml."""
    data = read_pyproject(repo_path)
    if "dependency-groups" not in data:
        data["dependency-groups"] = table()
    dep_groups: Any = data["dependency-groups"]
    if group not in dep_groups:
        dep_groups[group] = [package]
    else:
        dep_groups[group].append(package)
    write_pyproject(repo_path, data)


def add_package_with_uv(
    repo_path: Path,
    package: str,
    *,
    group: str | None = None,
    dev: bool = False,
) -> None:
    """Add a package using uv add, skipping if already present."""
    if is_package_in_deps(repo_path, package):
        logger.info(f"{package} already in dependencies, skipping uv add")
        return

    logger.info(f"Adding {package} dependency...")
    cmd = ["add", "--no-install-project"]
    if dev:
        cmd.append("--dev")
    elif group:
        cmd.extend(["--group", group])
    cmd.append(package)
    run_uv(repo_path, *cmd)


def verify_uv_present(repo_path: Path) -> None:
    """Verify that uv is installed and available."""
    try:
        result = run_uv(repo_path, "--version", check=False)
        if result.returncode != 0:
            msg = "uv is not available"
            raise BoostSkippedError(msg)
    except (FileNotFoundError, OSError) as e:
        msg = "uv is not installed"
        raise BoostSkippedError(msg) from e


def verify_pyproject_present(repo_path: Path) -> None:
    """Verify that pyproject.toml exists."""
    if not (repo_path / "pyproject.toml").exists():
        msg = "No pyproject.toml found"
        raise BoostSkippedError(msg)
