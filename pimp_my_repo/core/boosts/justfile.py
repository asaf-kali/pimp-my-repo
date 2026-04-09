"""Justfile boost implementation."""

import platform
import re
import shutil
from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger

from pimp_my_repo.core.boosts.base import Boost, BoostSkipped
from pimp_my_repo.core.tools.subprocess import run_command

if TYPE_CHECKING:
    from pathlib import Path

_INSTALL_COMMANDS_BY_OS: dict[str, list[list[str]]] = {
    "Linux": [
        ["brew", "install", "just"],
        ["snap", "install", "just", "--edge"],
        ["sudo", "apt-get", "install", "-y", "just"],
    ],
    "Darwin": [
        ["brew", "install", "just"],
    ],
    "Windows": [
        ["winget", "install", "--id", "Casey.Just"],
    ],
}

_RUN_VAR = 'RUN := "uv run"'

_RECIPE_INSTALL = "install:\n    uv sync --all-groups\n"
_RECIPE_FORMAT = "format:\n    {{ RUN }} ruff format\n"
_RECIPE_LINT_NO_PRECOMMIT = "lint: format\n    {{ RUN }} ruff check --fix --unsafe-fixes\n"
_RECIPE_LINT_WITH_PRECOMMIT = (
    "lint: format\n    {{ RUN }} ruff check --fix --unsafe-fixes\n    {{ RUN }} pre-commit run --all-files\n"
)
_RECIPE_CHECK_LOCK = "check-lock:\n    uv lock --check\n"
_RECIPE_CHECK_RUFF = "check-ruff:\n    {{ RUN }} ruff format --check\n    {{ RUN }} ruff check\n"
_RECIPE_CHECK_MYPY = "check-mypy:\n    {{ RUN }} mypy .\n"


@dataclass
class _JustfileConfig:
    """Configuration flags for justfile content generation."""

    existing_path: Path | None
    existing_recipes: set[str]
    has_pyproject: bool
    has_uv: bool
    has_ruff: bool
    has_mypy: bool
    has_precommit: bool


class JustfileBoost(Boost):
    """Boost for generating justfile with common commands."""

    def apply(self) -> None:
        """Generate or extend justfile with common commands."""
        if not _is_just_available():
            logger.info("just not found, attempting installation...")
            if not _try_install_just():
                msg = "just is not available and could not be installed"
                raise BoostSkipped(msg)

        justfile_path = self.repo_path / "justfile"
        existing_recipes = _get_existing_recipes(justfile_path) if justfile_path.exists() else set()

        config = _JustfileConfig(
            existing_path=justfile_path if justfile_path.exists() else None,
            existing_recipes=existing_recipes,
            has_pyproject=(self.repo_path / "pyproject.toml").exists(),
            has_uv=(self.repo_path / "uv.lock").exists(),
            has_ruff=_is_ruff_configured(self.repo_path),
            has_mypy=_is_mypy_configured(self.repo_path),
            has_precommit=(self.repo_path / ".pre-commit-config.yaml").exists(),
        )
        new_content = _build_content(config=config)

        if new_content is None:
            msg = "All justfile recipes already present"
            raise BoostSkipped(msg)

        self.git.write_file("justfile", new_content)

    def commit_message(self) -> str:
        """Generate commit message for justfile boost."""
        return "✨ Add justfile with common commands"


def _is_just_available() -> bool:
    """Check if just is available in PATH."""
    return shutil.which("just") is not None


def _try_install_just() -> bool:
    """Attempt to install just using a platform-appropriate package manager.

    Returns True if installation succeeded, False otherwise.
    """
    system = platform.system()
    commands = _INSTALL_COMMANDS_BY_OS.get(system, [])
    for cmd in commands:
        tool = next((c for c in cmd if c != "sudo"), None)
        if tool and not shutil.which(tool):
            logger.debug(f"Skipping {tool}: not in PATH")
            continue
        try:
            run_command(cmd)
        except Exception:  # noqa: BLE001
            logger.debug(f"Failed to install just via {cmd!r}")
        else:
            logger.info(f"Installed just via {tool}")
            return True
    return False


def _get_existing_recipes(justfile_path: Path) -> set[str]:
    """Parse a justfile and return the set of defined recipe names."""
    content = justfile_path.read_text(encoding="utf-8")
    recipes: set[str] = set()
    for line in content.splitlines():
        m = re.match(r"^([a-zA-Z0-9][a-zA-Z0-9_-]*)", line)
        if m and ":=" not in line and ":" in line:
            recipes.add(m.group(1))
    return recipes


def _is_ruff_configured(repo_path: Path) -> bool:
    """Return True if ruff is configured in pyproject.toml."""
    pyproject = repo_path / "pyproject.toml"
    return pyproject.exists() and "[tool.ruff" in pyproject.read_text(encoding="utf-8")


def _is_mypy_configured(repo_path: Path) -> bool:
    """Return True if mypy is configured in pyproject.toml."""
    pyproject = repo_path / "pyproject.toml"
    return pyproject.exists() and "[tool.mypy" in pyproject.read_text(encoding="utf-8")


def _select_recipes(*, config: _JustfileConfig) -> list[str]:
    """Return recipe blocks to add based on project configuration."""
    existing = config.existing_recipes
    recipes: list[str] = []
    if config.has_pyproject and "install" not in existing:
        recipes.append(_RECIPE_INSTALL)
    if config.has_uv and "check-lock" not in existing:
        recipes.append(_RECIPE_CHECK_LOCK)
    if config.has_ruff:
        if "format" not in existing:
            recipes.append(_RECIPE_FORMAT)
        if "lint" not in existing:
            lint = _RECIPE_LINT_WITH_PRECOMMIT if config.has_precommit else _RECIPE_LINT_NO_PRECOMMIT
            recipes.append(lint)
        if "check-ruff" not in existing:
            recipes.append(_RECIPE_CHECK_RUFF)
    if config.has_mypy and "check-mypy" not in existing:
        recipes.append(_RECIPE_CHECK_MYPY)
    return recipes


def _build_content(*, config: _JustfileConfig) -> str | None:
    """Build the new justfile content, or None if nothing needs to be added."""
    recipes = _select_recipes(config=config)
    if not recipes:
        return None

    body = "\n".join(recipes)
    needs_run_var = "{{ RUN }}" in body

    if config.existing_path is None:
        header = (_RUN_VAR + "\n\n") if needs_run_var else ""
        return header + body

    existing = config.existing_path.read_text(encoding="utf-8")
    run_defined = "RUN :=" in existing
    var_prefix = (_RUN_VAR + "\n\n") if (needs_run_var and not run_defined) else ""
    sep = "\n" if existing.endswith("\n") else "\n\n"
    return existing + sep + var_prefix + body
