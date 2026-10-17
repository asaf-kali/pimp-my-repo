"""Tests for GitHub Actions CI boost implementation."""

from dataclasses import dataclass
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
import yaml

from pimp_my_repo.core.boosts.base import BoostSkipped
from pimp_my_repo.core.boosts.github_actions import GithubActionsBoost
from pimp_my_repo.core.run_config import RunConfig

if TYPE_CHECKING:
    from collections.abc import Generator

    from pimp_my_repo.core.tools.boost_tools import BoostTools
    from pimp_my_repo.core.tools.repo import RepositoryController


_GITHUB_URL = "https://github.com/test/repo"
_GITLAB_URL = "https://gitlab.com/test/repo"
_WORKFLOW_FILE = ".github/workflows/ci.yml"
_PYPROJECT_RUFF_MYPY = "[project]\nname = 'x'\n[tool.ruff]\n[tool.mypy]\nstrict = true\n"
_PYPROJECT_TY = "[project]\nname = 'x'\n[tool.ty.rules]\n"
_JUSTFILE_FULL = (
    "check-lock:\n    uv lock --check\n"
    "check-ruff:\n    uv run ruff check\n"
    "check-mypy:\n    uv run mypy .\n"
    "check-ty:\n    uv run ty check .\n"
    "lint: format\n    uv run ruff check --fix\n"
)


def _run_commands(*, content: str) -> list[str]:
    workflow = yaml.safe_load(content)
    steps = workflow["jobs"]["checks"]["steps"]
    return [step["run"] for step in steps if "run" in step]


@pytest.fixture
def github_actions_boost(boost_tools: BoostTools) -> GithubActionsBoost:
    return GithubActionsBoost(boost_tools, RunConfig())


@dataclass
class PatchedGithubActionsApply:
    boost: GithubActionsBoost
    mock_get_origin_url: MagicMock
    repo: RepositoryController

    def apply_and_read(self) -> str:
        self.boost.apply()
        return (self.repo.path / _WORKFLOW_FILE).read_text(encoding="utf-8")

    def apply_and_run_commands(self) -> list[str]:
        content = self.apply_and_read()
        return _run_commands(content=content)


@pytest.fixture
def patched_github_actions(
    github_actions_boost: GithubActionsBoost,
    mock_repo: RepositoryController,
) -> Generator[PatchedGithubActionsApply]:
    with patch.object(github_actions_boost.git, "get_origin_url", return_value=_GITHUB_URL) as mock_get_origin_url:
        yield PatchedGithubActionsApply(
            boost=github_actions_boost, mock_get_origin_url=mock_get_origin_url, repo=mock_repo
        )


# =============================================================================
# SKIP CONDITIONS
# =============================================================================


def test_skip_no_remote(github_actions_boost: GithubActionsBoost) -> None:
    with (
        patch.object(github_actions_boost.git, "get_origin_url", side_effect=RuntimeError("no remote")),
        pytest.raises(BoostSkipped, match="No git remote configured"),
    ):
        github_actions_boost.apply()


def test_skip_non_github(github_actions_boost: GithubActionsBoost) -> None:
    with (
        patch.object(github_actions_boost.git, "get_origin_url", return_value=_GITLAB_URL),
        pytest.raises(BoostSkipped, match="Remote is not GitHub"),
    ):
        github_actions_boost.apply()


@pytest.mark.parametrize("existing_file", [".github/workflows/ci.yml", ".github/workflows/release.yaml"])
def test_skip_existing_workflow(patched_github_actions: PatchedGithubActionsApply, existing_file: str) -> None:
    patched_github_actions.repo.write_file(existing_file, "name: CI\n")
    with pytest.raises(BoostSkipped, match="CI workflow already exists"):
        patched_github_actions.boost.apply()


def test_idempotency(patched_github_actions: PatchedGithubActionsApply) -> None:
    patched_github_actions.boost.apply()
    with pytest.raises(BoostSkipped, match="CI workflow already exists"):
        patched_github_actions.boost.apply()


# =============================================================================
# WORKFLOW STRUCTURE
# =============================================================================


def test_workflow_is_valid_yaml_with_setup_steps(patched_github_actions: PatchedGithubActionsApply) -> None:
    content = patched_github_actions.apply_and_read()
    workflow = yaml.safe_load(content)
    assert workflow["name"] == "CI"
    assert "pull_request" in workflow[True]  # PyYAML parses the `on` key as boolean True
    assert workflow[True]["push"]["branches"] == ["main", "master"]
    uses = [step["uses"] for step in workflow["jobs"]["checks"]["steps"] if "uses" in step]
    assert uses == ["actions/checkout@v5", "astral-sh/setup-uv@v6"]
    assert "uv sync --all-groups --all-extras" in content


def test_no_tools_no_tests_only_installs(patched_github_actions: PatchedGithubActionsApply) -> None:
    commands = patched_github_actions.apply_and_run_commands()
    assert commands == ["uv sync --all-groups --all-extras"]


# =============================================================================
# JUSTFILE-DRIVEN STEPS
# =============================================================================


def test_justfile_recipes_preferred_over_raw_commands(patched_github_actions: PatchedGithubActionsApply) -> None:
    patched_github_actions.repo.write_file("pyproject.toml", _PYPROJECT_RUFF_MYPY)
    patched_github_actions.repo.write_file("uv.lock", "")
    patched_github_actions.repo.write_file("justfile", _JUSTFILE_FULL)
    content = patched_github_actions.apply_and_read()
    commands = _run_commands(content=content)
    assert "extractions/setup-just@v3" in content
    assert commands == ["uv sync --all-groups --all-extras", "just check-lock", "just check-ruff", "just check-mypy"]


def test_justfile_lint_recipe_never_used_in_ci(patched_github_actions: PatchedGithubActionsApply) -> None:
    patched_github_actions.repo.write_file("pyproject.toml", _PYPROJECT_RUFF_MYPY)
    patched_github_actions.repo.write_file("justfile", "lint: format\n    uv run ruff check --fix\n")
    content = patched_github_actions.apply_and_read()
    assert "just lint" not in content
    assert "uv run ruff format --check && uv run ruff check" in content
    assert "uv run mypy ." in content


def test_justfile_test_recipe_used_when_present(patched_github_actions: PatchedGithubActionsApply) -> None:
    patched_github_actions.repo.write_file("justfile", "test *args:\n    pytest {{ args }}\n")
    commands = patched_github_actions.apply_and_run_commands()
    assert commands[-1] == "just test"


def test_justfile_check_ty_recipe(patched_github_actions: PatchedGithubActionsApply) -> None:
    patched_github_actions.repo.write_file("pyproject.toml", _PYPROJECT_TY)
    patched_github_actions.repo.write_file("justfile", _JUSTFILE_FULL)
    commands = patched_github_actions.apply_and_run_commands()
    assert "just check-ty" in commands
    assert "just check-mypy" not in commands


# =============================================================================
# FALLBACK STEPS (NO JUSTFILE)
# =============================================================================


def test_no_justfile_ruff_and_mypy(patched_github_actions: PatchedGithubActionsApply) -> None:
    patched_github_actions.repo.write_file("pyproject.toml", _PYPROJECT_RUFF_MYPY)
    content = patched_github_actions.apply_and_read()
    assert "setup-just" not in content
    assert "uv run ruff format --check && uv run ruff check" in content
    assert "uv run mypy ." in content


def test_no_justfile_ty(patched_github_actions: PatchedGithubActionsApply) -> None:
    patched_github_actions.repo.write_file("pyproject.toml", _PYPROJECT_TY)
    commands = patched_github_actions.apply_and_run_commands()
    assert "uv run ty check ." in commands
    assert "uv run mypy ." not in commands


def test_uv_lock_adds_lock_check(patched_github_actions: PatchedGithubActionsApply) -> None:
    patched_github_actions.repo.write_file("uv.lock", "")
    commands = patched_github_actions.apply_and_run_commands()
    assert "uv lock --check" in commands


# =============================================================================
# TEST STEP DETECTION
# =============================================================================


@pytest.mark.parametrize("test_path", ["tests/test_a.py", "test/test_a.py", "src/pkg/test_a.py"])
def test_pytest_step_when_tests_exist(patched_github_actions: PatchedGithubActionsApply, test_path: str) -> None:
    patched_github_actions.repo.write_file(test_path, "def test_a() -> None: ...\n")
    commands = patched_github_actions.apply_and_run_commands()
    assert commands[-1] == "uv run pytest"


def test_no_pytest_step_for_tests_in_hidden_dirs(patched_github_actions: PatchedGithubActionsApply) -> None:
    patched_github_actions.repo.write_file(".venv/lib/site-packages/pkg/test_a.py", "")
    commands = patched_github_actions.apply_and_run_commands()
    assert "uv run pytest" not in commands


# =============================================================================
# PYTHON VERSION DETECTION
# =============================================================================


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        (">=3.11", "3.11"),
        (">=3.10,<4", "3.10"),
        ("~=3.9", "3.9"),
        ("==3.12.*", "3.12"),
        ("invalid", "3.12"),
    ],
)
def test_python_version_from_pyproject(
    patched_github_actions: PatchedGithubActionsApply, spec: str, expected: str
) -> None:
    patched_github_actions.repo.write_file("pyproject.toml", f'[project]\nname = "x"\nrequires-python = "{spec}"\n')
    content = patched_github_actions.apply_and_read()
    assert f"python-version: '{expected}'" in content


def test_python_version_fallback_when_no_pyproject(patched_github_actions: PatchedGithubActionsApply) -> None:
    content = patched_github_actions.apply_and_read()
    assert "python-version: '3.12'" in content


# =============================================================================
# MISC
# =============================================================================


def test_commit_message(github_actions_boost: GithubActionsBoost) -> None:
    assert github_actions_boost.commit_message() == "🚀 Add GitHub Actions CI workflow"


def test_get_name() -> None:
    assert GithubActionsBoost.get_name() == "github-actions"
