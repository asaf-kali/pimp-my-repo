"""Tests for GitHub Actions CI boost implementation."""

from dataclasses import dataclass
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from pimp_my_repo.core.boosts.base import BoostSkipped
from pimp_my_repo.core.boosts.github_actions import (
    _WORKFLOW_OUTPUT_FILE,
    GithubActionsBoost,
    _parse_python_version,
)
from pimp_my_repo.core.run_config import RunConfig

if TYPE_CHECKING:
    from collections.abc import Generator

    from pimp_my_repo.core.tools.boost_tools import BoostTools
    from pimp_my_repo.core.tools.repo import RepositoryController


_GITHUB_URL = "https://github.com/test/repo"
_GITLAB_URL = "https://gitlab.com/test/repo"


@pytest.fixture
def github_actions_boost(boost_tools: BoostTools) -> GithubActionsBoost:
    return GithubActionsBoost(boost_tools, RunConfig())


@dataclass
class PatchedGithubActionsApply:
    boost: GithubActionsBoost
    mock_get_origin_url: MagicMock


@pytest.fixture
def patched_github_actions(
    github_actions_boost: GithubActionsBoost,
) -> Generator[PatchedGithubActionsApply]:
    with patch.object(
        github_actions_boost.git,
        "get_origin_url",
        return_value=_GITHUB_URL,
    ) as mock_get_origin_url:
        yield PatchedGithubActionsApply(
            boost=github_actions_boost,
            mock_get_origin_url=mock_get_origin_url,
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


def test_skip_existing_yml_workflow(
    mock_repo: RepositoryController,
    patched_github_actions: PatchedGithubActionsApply,
) -> None:
    mock_repo.write_file(".github/workflows/ci.yml", "name: CI\n")
    with pytest.raises(BoostSkipped, match="CI workflow already exists"):
        patched_github_actions.boost.apply()


def test_skip_existing_yaml_workflow(
    mock_repo: RepositoryController,
    patched_github_actions: PatchedGithubActionsApply,
) -> None:
    mock_repo.write_file(".github/workflows/ci.yaml", "name: CI\n")
    with pytest.raises(BoostSkipped, match="CI workflow already exists"):
        patched_github_actions.boost.apply()


# =============================================================================
# APPLY — WORKFLOW CONTENT
# =============================================================================


def test_apply_with_justfile(
    mock_repo: RepositoryController,
    patched_github_actions: PatchedGithubActionsApply,
) -> None:
    mock_repo.write_file("justfile", "lint:\n    uv run ruff check .\n")
    patched_github_actions.boost.apply()
    content = (mock_repo.path / _WORKFLOW_OUTPUT_FILE).read_text(encoding="utf-8")
    assert "just lint" in content
    assert "just test" in content
    assert "uv run ruff" not in content
    assert "uv run mypy" not in content


def test_apply_no_justfile_ruff_and_mypy(
    mock_repo: RepositoryController,
    patched_github_actions: PatchedGithubActionsApply,
) -> None:
    mock_repo.write_file(
        "pyproject.toml",
        "[project]\nname = 'x'\n[tool.ruff]\n[tool.mypy]\nstrict = true\n",
    )
    patched_github_actions.boost.apply()
    content = (mock_repo.path / _WORKFLOW_OUTPUT_FILE).read_text(encoding="utf-8")
    assert "uv run ruff check" in content
    assert "uv run mypy" in content
    assert "uv run pytest" in content
    assert "just lint" not in content


def test_apply_no_justfile_no_tools(
    patched_github_actions: PatchedGithubActionsApply,
    mock_repo: RepositoryController,
) -> None:
    patched_github_actions.boost.apply()
    content = (mock_repo.path / _WORKFLOW_OUTPUT_FILE).read_text(encoding="utf-8")
    assert "uv run pytest" in content
    assert "just lint" not in content
    assert "uv run ruff" not in content
    assert "uv run mypy" not in content


def test_apply_creates_workflow_file(
    mock_repo: RepositoryController,
    patched_github_actions: PatchedGithubActionsApply,
) -> None:
    patched_github_actions.boost.apply()
    assert (mock_repo.path / _WORKFLOW_OUTPUT_FILE).exists()


def test_apply_workflow_contains_setup_uv(
    mock_repo: RepositoryController,
    patched_github_actions: PatchedGithubActionsApply,
) -> None:
    patched_github_actions.boost.apply()
    content = (mock_repo.path / _WORKFLOW_OUTPUT_FILE).read_text(encoding="utf-8")
    assert "astral-sh/setup-uv" in content
    assert "uv sync --all-extras" in content
    assert "actions/checkout" in content


# =============================================================================
# PYTHON VERSION DETECTION
# =============================================================================


def test_python_version_from_pyproject(
    mock_repo: RepositoryController,
    patched_github_actions: PatchedGithubActionsApply,
) -> None:
    mock_repo.write_file(
        "pyproject.toml",
        '[project]\nname = "x"\nrequires-python = ">=3.11"\n',
    )
    patched_github_actions.boost.apply()
    content = (mock_repo.path / _WORKFLOW_OUTPUT_FILE).read_text(encoding="utf-8")
    assert "python-version: '3.11'" in content


def test_python_version_fallback_when_no_pyproject(
    patched_github_actions: PatchedGithubActionsApply,
    mock_repo: RepositoryController,
) -> None:
    patched_github_actions.boost.apply()
    content = (mock_repo.path / _WORKFLOW_OUTPUT_FILE).read_text(encoding="utf-8")
    assert "python-version: '3.12'" in content


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        (">=3.11", "3.11"),
        (">=3.10,<4", "3.10"),
        ("~=3.9", "3.9"),
        ("==3.12.*", "3.12"),
        ("", "3.12"),
        ("invalid", "3.12"),
    ],
)
def test_parse_python_version(spec: str, expected: str) -> None:
    pyproject_text = f'[project]\nrequires-python = "{spec}"\n' if spec else ""
    assert _parse_python_version(pyproject_text) == expected


# =============================================================================
# IDEMPOTENCY
# =============================================================================


def test_idempotency(
    patched_github_actions: PatchedGithubActionsApply,
) -> None:
    patched_github_actions.boost.apply()
    with pytest.raises(BoostSkipped, match="CI workflow already exists"):
        patched_github_actions.boost.apply()


# =============================================================================
# MISC
# =============================================================================


def test_commit_message(github_actions_boost: GithubActionsBoost) -> None:
    assert github_actions_boost.commit_message() == "🚀 Add GitHub Actions CI workflow"


def test_get_name() -> None:
    assert GithubActionsBoost.get_name() == "github-actions"
