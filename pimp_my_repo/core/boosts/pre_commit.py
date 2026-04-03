"""Pre-commit boost implementation."""

import re
from typing import TYPE_CHECKING

from loguru import logger

from pimp_my_repo.core.boosts.base import Boost, BoostSkippedError
from pimp_my_repo.core.tools.pyproject import PyProjectNotFoundError
from pimp_my_repo.core.tools.uv import UvNotFoundError

if TYPE_CHECKING:
    from pathlib import Path

_CONFIG_FILE = ".pre-commit-config.yaml"

_PMR_MARKER = "# pimp-my-repo:pre-commit"

_STANDARD_HOOKS = f"""\
{_PMR_MARKER}
# See https://pre-commit.com for more information
# See https://pre-commit.com/hooks.html for more hooks
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
"""

_LOCAL_HOOKS_HEADER = "  - repo: local\n    hooks:\n"

_HOOK_CHECK_LOCK = (
    "      - id: check-uv-lock\n"
    "        name: check uv lock\n"
    '        entry: "just check-lock"\n'
    "        language: system\n"
    "        pass_filenames: false\n"
)

_HOOK_CHECK_RUFF = (
    "      - id: check-ruff\n"
    "        name: check ruff standard\n"
    '        entry: "just check-ruff"\n'
    "        language: system\n"
    "        pass_filenames: false\n"
)

_HOOK_CHECK_MYPY = (
    "      - id: check-mypy\n"
    "        name: check mypy typing\n"
    '        entry: "just check-mypy"\n'
    "        language: system\n"
    "        pass_filenames: false\n"
)


class PreCommitBoost(Boost):
    """Boost for integrating pre-commit hooks."""

    def apply(self) -> None:
        """Create pre-commit config and install hooks."""
        if (self.repo_path / _CONFIG_FILE).exists():
            msg = f"{_CONFIG_FILE} already exists"
            raise BoostSkippedError(msg)

        try:
            self.uv.verify_present()
        except UvNotFoundError as exc:
            msg = "uv is not available"
            raise BoostSkippedError(msg) from exc

        try:
            self.pyproject.verify_present()
        except PyProjectNotFoundError as exc:
            msg = "No pyproject.toml found"
            raise BoostSkippedError(msg) from exc

        logger.debug("Adding pre-commit to dev dependencies...")
        self.uv.add_package("pre-commit", group="dev")

        logger.debug("Generating pre-commit config...")
        justfile_recipes = _get_justfile_recipes(self.repo_path)
        config_content = _build_config(justfile_recipes=justfile_recipes)
        self.git.write_file(_CONFIG_FILE, config_content)

        logger.debug("Installing pre-commit hooks...")
        self.uv.exec("run", "pre-commit", "install")

        logger.debug("Running pre-commit hooks on all files to auto-fix any existing issues...")
        self.uv.exec("run", "--no-sync", "pre-commit", "run", "--all-files", check=False, log_on_error=False)

    def commit_message(self) -> str:
        """Generate commit message for pre-commit boost."""
        return "✨ Add pre-commit hooks"


def _get_justfile_recipes(repo_path: Path) -> set[str]:
    """Return the set of recipe names defined in the justfile, or empty set if absent."""
    logger.debug("Checking for justfile recipes to include in pre-commit config...")
    justfile_path = repo_path / "justfile"
    if not justfile_path.exists():
        return set()
    content = justfile_path.read_text(encoding="utf-8")
    recipes: set[str] = set()
    for line in content.splitlines():
        m = re.match(r"^([a-zA-Z0-9][a-zA-Z0-9_-]*)", line)
        if m and ":=" not in line and ":" in line:
            recipes.add(m.group(1))
    logger.debug(f"Found justfile recipes: {recipes}")
    return recipes


def _build_config(*, justfile_recipes: set[str]) -> str:
    """Build .pre-commit-config.yaml content based on available justfile recipes."""
    logger.debug("Building pre-commit config based on justfile recipes...")
    local_hooks: list[str] = []
    if "check-lock" in justfile_recipes:
        local_hooks.append(_HOOK_CHECK_LOCK)
    if "check-ruff" in justfile_recipes:
        local_hooks.append(_HOOK_CHECK_RUFF)
    if "check-mypy" in justfile_recipes:
        local_hooks.append(_HOOK_CHECK_MYPY)

    content = _STANDARD_HOOKS
    if local_hooks:
        content += _LOCAL_HOOKS_HEADER + "".join(local_hooks)
    logger.trace(f"Generated pre-commit config content:\n{content}")
    return content
