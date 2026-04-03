"""Tests for PreCommitBoost implementation."""

from dataclasses import dataclass
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from pimp_my_repo.core.boosts.base import BoostSkipped
from pimp_my_repo.core.boosts.pre_commit import PreCommitBoost
from pimp_my_repo.core.tools.uv import UvNotFoundError

if TYPE_CHECKING:
    from collections.abc import Generator

    from pimp_my_repo.core.tools.boost_tools import BoostTools
    from pimp_my_repo.core.tools.repo import RepositoryController
    from tests.conftest import SubprocessResultFactory


@pytest.fixture
def pre_commit_boost(boost_tools: BoostTools) -> PreCommitBoost:
    return PreCommitBoost(boost_tools)


@pytest.fixture
def pre_commit_boost_with_pyproject(
    boost_tools: BoostTools,
    mock_repo: RepositoryController,
) -> PreCommitBoost:
    mock_repo.write_file("pyproject.toml", "[project]\nname = 'test'\n")
    return PreCommitBoost(boost_tools)


@dataclass
class PatchedPreCommitApply:
    """PreCommitBoost with subprocess calls pre-mocked."""

    boost: PreCommitBoost
    mock_add_package: MagicMock
    mock_uv_exec: MagicMock


@pytest.fixture
def patched_pre_commit_apply(
    pre_commit_boost_with_pyproject: PreCommitBoost,
    ok_result: SubprocessResultFactory,
) -> Generator[PatchedPreCommitApply]:
    with (
        patch.object(pre_commit_boost_with_pyproject.uv, "add_package") as mock_add,
        patch.object(pre_commit_boost_with_pyproject.uv, "exec", return_value=ok_result()) as mock_exec,
    ):
        yield PatchedPreCommitApply(
            boost=pre_commit_boost_with_pyproject,
            mock_add_package=mock_add,
            mock_uv_exec=mock_exec,
        )


# --- Skip conditions ---


@pytest.mark.smoke
def test_skips_when_config_already_exists(
    mock_repo: RepositoryController,
    pre_commit_boost: PreCommitBoost,
) -> None:
    mock_repo.write_file(".pre-commit-config.yaml", "repos: []\n")
    with pytest.raises(BoostSkipped, match="already exists"):
        pre_commit_boost.apply()


def test_skips_when_uv_not_present(
    mock_repo: RepositoryController,
    pre_commit_boost: PreCommitBoost,
) -> None:
    mock_repo.write_file("pyproject.toml", "[project]\nname = 'test'\n")
    with (
        patch.object(pre_commit_boost.uv, "verify_present", side_effect=UvNotFoundError("no uv")),
        pytest.raises(BoostSkipped, match="uv is not available"),
    ):
        pre_commit_boost.apply()


def test_skips_when_no_pyproject(pre_commit_boost: PreCommitBoost) -> None:
    with (
        patch.object(pre_commit_boost.uv, "verify_present"),
        pytest.raises(BoostSkipped, match=r"No pyproject\.toml found"),
    ):
        pre_commit_boost.apply()


# --- Happy paths ---


@pytest.mark.smoke
def test_happy_path_no_justfile_writes_standard_hooks_only(
    mock_repo: RepositoryController,
    patched_pre_commit_apply: PatchedPreCommitApply,
) -> None:
    patched_pre_commit_apply.boost.apply()

    content = (mock_repo.path / ".pre-commit-config.yaml").read_text()
    assert "pre-commit/pre-commit-hooks" in content
    assert "trailing-whitespace" in content
    assert "check-yaml" in content
    assert "repo: local" not in content


@pytest.mark.smoke
def test_happy_path_with_ruff_and_mypy_recipes(
    mock_repo: RepositoryController,
    patched_pre_commit_apply: PatchedPreCommitApply,
) -> None:
    mock_repo.write_file(
        "justfile",
        "check-ruff:\n    uv run ruff check\n\ncheck-mypy:\n    uv run mypy .\n",
    )

    patched_pre_commit_apply.boost.apply()

    content = (mock_repo.path / ".pre-commit-config.yaml").read_text()
    assert "repo: local" in content
    assert "just check-ruff" in content
    assert "just check-mypy" in content
    assert "check-uv-lock" not in content


def test_includes_only_check_ruff_when_only_ruff_recipe_present(
    mock_repo: RepositoryController,
    patched_pre_commit_apply: PatchedPreCommitApply,
) -> None:
    mock_repo.write_file("justfile", "check-ruff:\n    uv run ruff check\n")

    patched_pre_commit_apply.boost.apply()

    content = (mock_repo.path / ".pre-commit-config.yaml").read_text()
    assert "check-ruff" in content
    assert "check-mypy" not in content


def test_includes_check_lock_when_recipe_present(
    mock_repo: RepositoryController,
    patched_pre_commit_apply: PatchedPreCommitApply,
) -> None:
    mock_repo.write_file(
        "justfile",
        "check-lock:\n    uv lock --check\n\ncheck-ruff:\n    uv run ruff check\n",
    )

    patched_pre_commit_apply.boost.apply()

    content = (mock_repo.path / ".pre-commit-config.yaml").read_text()
    assert "check-uv-lock" in content
    assert "just check-lock" in content


# --- Subprocess call verification ---


def test_calls_pre_commit_install(patched_pre_commit_apply: PatchedPreCommitApply) -> None:
    patched_pre_commit_apply.boost.apply()
    patched_pre_commit_apply.mock_uv_exec.assert_any_call("run", "pre-commit", "install")


def test_adds_pre_commit_as_dev_dependency(patched_pre_commit_apply: PatchedPreCommitApply) -> None:
    patched_pre_commit_apply.boost.apply()
    patched_pre_commit_apply.mock_add_package.assert_called_once_with("pre-commit", group="dev")


# --- Metadata ---


def test_commit_message(pre_commit_boost: PreCommitBoost) -> None:
    assert pre_commit_boost.commit_message() == "✨ Add pre-commit hooks"


def test_get_name() -> None:
    assert PreCommitBoost.get_name() == "precommit"
