"""PyProject.toml operations controller for boosts."""

import re
from typing import TYPE_CHECKING

from tomlkit import TOMLDocument, dumps, loads, table

from pimp_my_repo.core.boosts.base import BoostSkippedError

if TYPE_CHECKING:
    from pathlib import Path
    from typing import Any


class PyProjectController:
    """Controller for pyproject.toml operations in boosts."""

    def __init__(self, repo_path: Path) -> None:
        """Initialize PyProjectController with repository path."""
        self.repo_path = repo_path

    def read(self) -> TOMLDocument:
        """Read existing pyproject.toml if it exists."""
        pyproject_path = self.repo_path / "pyproject.toml"
        with pyproject_path.open(encoding="utf-8") as f:
            return loads(f.read())

    def write(self, data: TOMLDocument) -> None:
        """Write pyproject.toml."""
        pyproject_path = self.repo_path / "pyproject.toml"
        with pyproject_path.open("w", encoding="utf-8") as f:
            f.write(dumps(data))

    def is_package_in_deps(self, package: str) -> bool:
        """Check if a package is already present in any dependency group in pyproject.toml."""
        try:
            data = self.read()
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

    def add_package_to_deps(self, group: str, package: str) -> None:
        """Add a package to a dependency group directly in pyproject.toml."""
        data = self.read()
        if "dependency-groups" not in data:
            data["dependency-groups"] = table()
        dep_groups: Any = data["dependency-groups"]
        if group not in dep_groups:
            dep_groups[group] = [package]
        else:
            dep_groups[group].append(package)
        self.write(data)

    def verify_present(self) -> None:
        """Verify that pyproject.toml exists."""
        if not (self.repo_path / "pyproject.toml").exists():
            msg = "No pyproject.toml found"
            raise BoostSkippedError(msg)
