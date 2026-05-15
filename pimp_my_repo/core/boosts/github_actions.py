"""GitHub Actions CI boost implementation."""

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger

from pimp_my_repo.core.boosts.base import Boost, BoostSkipped

if TYPE_CHECKING:
    from pathlib import Path

_logger = logger.bind(boost="github_actions")

_DEFAULT_PYTHON_VERSION = "3.12"
_WORKFLOW_OUTPUT_FILE = ".github/workflows/ci.yml"

_WORKFLOW_HEADER = """\
name: CI

on:
  push:
  pull_request:

jobs:
  ci:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up uv
        uses: astral-sh/setup-uv@v5
        with:
          python-version: '{python_version}'
      - name: Install dependencies
        run: uv sync --all-extras
"""

_STEP_LINT_JUST = """\
      - name: Lint
        run: just lint
"""

_STEP_TEST_JUST = """\
      - name: Test
        run: just test
"""

_STEP_LINT_RUFF = """\
      - name: Lint
        run: uv run ruff check . && uv run ruff format --check .
"""

_STEP_TYPE_CHECK_MYPY = """\
      - name: Type check
        run: uv run mypy .
"""

_STEP_TEST_PYTEST = """\
      - name: Test
        run: uv run pytest
"""


@dataclass
class _CIConfig:
    python_version: str
    has_justfile: bool
    has_ruff: bool
    has_mypy: bool


class GithubActionsBoost(Boost):
    """Boost that generates a GitHub Actions CI workflow."""

    def apply(self) -> None:
        """Generate .github/workflows/ci.yml, skipping if origin isn't GitHub or CI already exists."""
        self._check_github_origin()
        self._check_no_existing_workflows()
        config = _detect_config(self.repo_path)
        content = _build_workflow(config=config)
        self.git.write_file(_WORKFLOW_OUTPUT_FILE, content)

    @classmethod
    def get_name(cls) -> str:
        return "github-actions"

    def commit_message(self) -> str:
        """Return commit message for the CI workflow file."""
        return "🚀 Add GitHub Actions CI workflow"

    def _check_github_origin(self) -> None:
        try:
            url = self.git.get_origin_url()
        except Exception:  # noqa: BLE001
            msg = "No git remote configured"
            raise BoostSkipped(msg) from None
        if "github.com" not in url:
            msg = f"Remote is not GitHub: {url}"
            raise BoostSkipped(msg)

    def _check_no_existing_workflows(self) -> None:
        workflows_dir = self.repo_path / ".github" / "workflows"
        if not workflows_dir.exists():
            return
        existing = [*workflows_dir.glob("*.yml"), *workflows_dir.glob("*.yaml")]
        if existing:
            msg = "CI workflow already exists"
            raise BoostSkipped(msg)


def _detect_config(repo_path: Path) -> _CIConfig:
    pyproject_path = repo_path / "pyproject.toml"
    pyproject_text = pyproject_path.read_text(encoding="utf-8") if pyproject_path.exists() else ""
    return _CIConfig(
        python_version=_parse_python_version(pyproject_text),
        has_justfile=(repo_path / "justfile").exists(),
        has_ruff="[tool.ruff" in pyproject_text,
        has_mypy="[tool.mypy" in pyproject_text,
    )


def _parse_python_version(pyproject_text: str) -> str:
    m = re.search(r'requires-python\s*=\s*["\']([^"\']+)["\']', pyproject_text)
    if not m:
        return _DEFAULT_PYTHON_VERSION
    spec = m.group(1)
    version_match = re.search(r"(\d+\.\d+)", spec)
    if not version_match:
        return _DEFAULT_PYTHON_VERSION
    return version_match.group(1)


def _build_workflow(*, config: _CIConfig) -> str:
    header = _WORKFLOW_HEADER.format(python_version=config.python_version)
    steps = _build_steps(config=config)
    return header + steps


def _build_steps(*, config: _CIConfig) -> str:
    if config.has_justfile:
        return _STEP_LINT_JUST + _STEP_TEST_JUST
    steps = ""
    if config.has_ruff:
        steps += _STEP_LINT_RUFF
    if config.has_mypy:
        steps += _STEP_TYPE_CHECK_MYPY
    steps += _STEP_TEST_PYTEST
    return steps
