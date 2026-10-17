"""GitHub Actions CI boost implementation."""

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from loguru import logger

from pimp_my_repo.core.boosts.base import Boost, BoostSkipped
from pimp_my_repo.core.tools.detect import get_justfile_recipes, has_tests, has_tool_section

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class _Step:
    """A single GitHub Actions job step."""

    name: str
    run: str | None = None
    uses: str | None = None
    with_: dict[str, str] = field(default_factory=dict)

    def render(self) -> str:
        lines = [f"      - name: {self.name}"]
        if self.uses is not None:
            lines.append(f"        uses: {self.uses}")
        if self.with_:
            lines.append("        with:")
            lines.extend(f"          {key}: {value}" for key, value in self.with_.items())
        if self.run is not None:
            lines.append(f"        run: {self.run}")
        return "\n".join(lines) + "\n"


@dataclass
class _CIConfig:
    """Detected repository features that shape the generated workflow."""

    python_version: str
    has_uv_lock: bool
    has_ruff: bool
    has_mypy: bool
    has_ty: bool
    has_tests: bool
    justfile_recipes: set[str]

    @property
    def has_justfile(self) -> bool:
        return bool(self.justfile_recipes)


_DEFAULT_PYTHON_VERSION = "3.12"
_WORKFLOW_OUTPUT_FILE = ".github/workflows/ci.yml"
_REQUIRES_PYTHON_PATTERN = re.compile(r"""requires-python\s*=\s*["']([^"']+)["']""")
_MINOR_VERSION_PATTERN = re.compile(r"(\d+\.\d+)")

_WORKFLOW_HEADER = """\
name: CI

on:
  push:
    branches: [main, master]
  pull_request:

jobs:
  checks:
    runs-on: ubuntu-latest
    steps:
"""

_RUFF_FALLBACK_COMMAND = "uv run ruff format --check && uv run ruff check"
_MYPY_FALLBACK_COMMAND = "uv run mypy ."
_TY_FALLBACK_COMMAND = "uv run ty check ."
_LOCK_FALLBACK_COMMAND = "uv lock --check"
_TEST_FALLBACK_COMMAND = "uv run pytest"


class GithubActionsBoost(Boost):
    """Boost that generates a GitHub Actions CI workflow."""

    def apply(self) -> None:
        """Generate .github/workflows/ci.yml, skipping if origin isn't GitHub or CI already exists."""
        self._check_github_origin()
        self._check_no_existing_workflows()
        config = _detect_config(repo_path=self.repo_path)
        logger.debug(f"Detected CI config: {config}")
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


def _detect_config(*, repo_path: Path) -> _CIConfig:
    justfile_path = repo_path / "justfile"
    recipes = get_justfile_recipes(justfile_path=justfile_path) if justfile_path.exists() else set()
    return _CIConfig(
        python_version=_detect_python_version(repo_path=repo_path),
        has_uv_lock=(repo_path / "uv.lock").exists(),
        has_ruff=has_tool_section(repo_path=repo_path, tool="ruff"),
        has_mypy=has_tool_section(repo_path=repo_path, tool="mypy"),
        has_ty=has_tool_section(repo_path=repo_path, tool="ty"),
        has_tests=has_tests(repo_path=repo_path),
        justfile_recipes=recipes,
    )


def _detect_python_version(*, repo_path: Path) -> str:
    pyproject_path = repo_path / "pyproject.toml"
    if not pyproject_path.exists():
        return _DEFAULT_PYTHON_VERSION
    pyproject_text = pyproject_path.read_text(encoding="utf-8")
    return _parse_python_version(pyproject_text=pyproject_text)


def _parse_python_version(*, pyproject_text: str) -> str:
    spec_match = _REQUIRES_PYTHON_PATTERN.search(pyproject_text)
    if not spec_match:
        return _DEFAULT_PYTHON_VERSION
    version_match = _MINOR_VERSION_PATTERN.search(spec_match.group(1))
    if not version_match:
        return _DEFAULT_PYTHON_VERSION
    return version_match.group(1)


def _build_workflow(*, config: _CIConfig) -> str:
    steps = _setup_steps(config=config) + _check_steps(config=config) + _test_steps(config=config)
    rendered_steps = "".join(step.render() for step in steps)
    return _WORKFLOW_HEADER + rendered_steps


def _setup_steps(*, config: _CIConfig) -> list[_Step]:
    steps = [
        _Step(name="Checkout", uses="actions/checkout@v5"),
        _Step(
            name="Set up uv",
            uses="astral-sh/setup-uv@v6",
            with_={"python-version": f"'{config.python_version}'", "enable-cache": "true"},
        ),
    ]
    if config.has_justfile:
        steps.append(_Step(name="Set up just", uses="extractions/setup-just@v3"))
    steps.append(_Step(name="Install dependencies", run="uv sync --all-groups --all-extras"))
    return steps


def _check_steps(*, config: _CIConfig) -> list[_Step]:
    steps: list[_Step] = []
    if config.has_uv_lock:
        steps.append(
            _recipe_or_fallback(config=config, name="Check lock", recipe="check-lock", fallback=_LOCK_FALLBACK_COMMAND)
        )
    if config.has_ruff:
        steps.append(
            _recipe_or_fallback(config=config, name="Check ruff", recipe="check-ruff", fallback=_RUFF_FALLBACK_COMMAND)
        )
    if config.has_mypy:
        steps.append(
            _recipe_or_fallback(config=config, name="Check mypy", recipe="check-mypy", fallback=_MYPY_FALLBACK_COMMAND)
        )
    if config.has_ty:
        steps.append(
            _recipe_or_fallback(config=config, name="Check ty", recipe="check-ty", fallback=_TY_FALLBACK_COMMAND)
        )
    return steps


def _test_steps(*, config: _CIConfig) -> list[_Step]:
    if "test" in config.justfile_recipes:
        return [_Step(name="Test", run="just test")]
    if config.has_tests:
        return [_Step(name="Test", run=_TEST_FALLBACK_COMMAND)]
    return []


def _recipe_or_fallback(*, config: _CIConfig, name: str, recipe: str, fallback: str) -> _Step:
    """Prefer the justfile recipe when present so CI and local runs stay in sync."""
    run = f"just {recipe}" if recipe in config.justfile_recipes else fallback
    return _Step(name=name, run=run)
