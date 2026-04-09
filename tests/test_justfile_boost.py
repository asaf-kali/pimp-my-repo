"""Tests for JustfileBoost implementation."""

import shutil
from dataclasses import dataclass
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

import pimp_my_repo.core.boosts.justfile as justfile_module
from pimp_my_repo.core.boosts.base import BoostSkipped
from pimp_my_repo.core.boosts.justfile import JustfileBoost

if TYPE_CHECKING:
    from collections.abc import Generator

    from pimp_my_repo.core.tools.boost_tools import BoostTools
    from pimp_my_repo.core.tools.repo import RepositoryController


@pytest.fixture
def justfile_boost(boost_tools: BoostTools) -> JustfileBoost:
    return JustfileBoost(boost_tools)


@dataclass
class PatchedJustfileApply:
    """JustfileBoost with just available, external calls pre-mocked."""

    boost: JustfileBoost
    mock_just_available: MagicMock


@pytest.fixture
def patched_justfile_apply(justfile_boost: JustfileBoost) -> Generator[PatchedJustfileApply]:
    """Yield a JustfileBoost where just is available in PATH."""
    with patch.object(justfile_module, "_is_just_available", return_value=True) as mock_available:
        yield PatchedJustfileApply(boost=justfile_boost, mock_just_available=mock_available)


@dataclass
class JustNotInstallable:
    """JustfileBoost where just cannot be found or installed."""

    boost: JustfileBoost


@pytest.fixture
def just_not_installable(justfile_boost: JustfileBoost) -> Generator[JustNotInstallable]:
    with (
        patch.object(justfile_module, "_is_just_available", return_value=False),
        patch.object(justfile_module, "_try_install_just", return_value=False),
    ):
        yield JustNotInstallable(boost=justfile_boost)


@dataclass
class JustInstalledOnDemand:
    """JustfileBoost where just is absent but installs successfully."""

    boost: JustfileBoost


@pytest.fixture
def just_installed_on_demand(justfile_boost: JustfileBoost) -> Generator[JustInstalledOnDemand]:
    with (
        patch.object(justfile_module, "_is_just_available", return_value=False),
        patch.object(justfile_module, "_try_install_just", return_value=True),
    ):
        yield JustInstalledOnDemand(boost=justfile_boost)


@pytest.fixture
def no_package_managers() -> Generator[None]:
    """Simulate an environment where no package manager is available."""
    with patch.object(shutil, "which", return_value=None):
        yield


@dataclass
class AllInstallCommandsFail:
    """Environment where brew is found but all install commands fail."""

    mock_run_command: MagicMock


@pytest.fixture
def all_install_commands_fail() -> Generator[AllInstallCommandsFail]:
    with (
        patch.object(shutil, "which", return_value="/usr/bin/brew"),
        patch.object(justfile_module, "run_command", side_effect=Exception("fail")) as mock_run,
    ):
        yield AllInstallCommandsFail(mock_run_command=mock_run)


# =============================================================================
# JUST AVAILABILITY & INSTALLATION
# =============================================================================


@pytest.mark.smoke
def test_skips_when_just_not_installable(just_not_installable: JustNotInstallable) -> None:
    with pytest.raises(BoostSkipped, match="just is not available"):
        just_not_installable.boost.apply()


def test_proceeds_when_just_installed_on_demand(
    mock_repo: RepositoryController,
    just_installed_on_demand: JustInstalledOnDemand,
) -> None:
    mock_repo.write_file("pyproject.toml", "[project]\nname = 'test'\n")
    just_installed_on_demand.boost.apply()
    assert (mock_repo.path / "justfile").exists()


def test_try_install_skips_missing_package_managers(no_package_managers: None) -> None:  # noqa: ARG001
    result = justfile_module._try_install_just()  # noqa: SLF001
    assert result is False


def test_try_install_returns_false_when_all_commands_fail(
    all_install_commands_fail: AllInstallCommandsFail,  # noqa: ARG001
) -> None:
    result = justfile_module._try_install_just()  # noqa: SLF001
    assert result is False


# =============================================================================
# NEW JUSTFILE CREATION
# =============================================================================


@pytest.mark.smoke
def test_creates_justfile_with_install_only(
    mock_repo: RepositoryController,
    patched_justfile_apply: PatchedJustfileApply,
) -> None:
    mock_repo.write_file("pyproject.toml", "[project]\nname = 'test'\n")
    patched_justfile_apply.boost.apply()
    content = (mock_repo.path / "justfile").read_text()
    assert "install:" in content
    assert "uv sync --all-groups" in content
    assert "format:" not in content
    assert "RUN :=" not in content


@pytest.mark.smoke
def test_creates_justfile_with_ruff_recipes(
    mock_repo: RepositoryController,
    patched_justfile_apply: PatchedJustfileApply,
) -> None:
    mock_repo.write_file("pyproject.toml", "[project]\n[tool.ruff]\n")
    patched_justfile_apply.boost.apply()
    content = (mock_repo.path / "justfile").read_text()
    assert 'RUN := "uv run"' in content
    assert "install:" in content
    assert "format:" in content
    assert "lint: format" in content
    assert "check-ruff:" in content
    assert "ruff format --check" in content
    assert "check-mypy:" not in content


def test_creates_justfile_with_mypy_recipe(
    mock_repo: RepositoryController,
    patched_justfile_apply: PatchedJustfileApply,
) -> None:
    mock_repo.write_file("pyproject.toml", "[project]\n[tool.mypy]\n")
    patched_justfile_apply.boost.apply()
    content = (mock_repo.path / "justfile").read_text()
    assert "check-mypy:" in content
    assert "mypy ." in content
    assert "format:" not in content


def test_creates_check_lock_recipe_when_uv_lock_present(
    mock_repo: RepositoryController,
    patched_justfile_apply: PatchedJustfileApply,
) -> None:
    mock_repo.write_file("pyproject.toml", "[project]\nname = 'test'\n")
    mock_repo.write_file("uv.lock", "")
    patched_justfile_apply.boost.apply()
    content = (mock_repo.path / "justfile").read_text()
    assert "check-lock:" in content
    assert "uv lock --check" in content


def test_includes_precommit_in_lint_when_config_present(
    mock_repo: RepositoryController,
    patched_justfile_apply: PatchedJustfileApply,
) -> None:
    mock_repo.write_file("pyproject.toml", "[tool.ruff]\n")
    mock_repo.write_file(".pre-commit-config.yaml", "repos: []\n")
    patched_justfile_apply.boost.apply()
    content = (mock_repo.path / "justfile").read_text()
    assert "pre-commit run --all-files" in content


def test_excludes_precommit_from_lint_when_no_config(
    mock_repo: RepositoryController,
    patched_justfile_apply: PatchedJustfileApply,
) -> None:
    mock_repo.write_file("pyproject.toml", "[tool.ruff]\n")
    patched_justfile_apply.boost.apply()
    content = (mock_repo.path / "justfile").read_text()
    assert "pre-commit" not in content


def test_skips_when_no_pyproject_and_no_tools(
    patched_justfile_apply: PatchedJustfileApply,
) -> None:
    with pytest.raises(BoostSkipped):
        patched_justfile_apply.boost.apply()


# =============================================================================
# APPENDING TO EXISTING JUSTFILE
# =============================================================================


def test_appends_missing_recipes_to_existing_justfile(
    mock_repo: RepositoryController,
    patched_justfile_apply: PatchedJustfileApply,
) -> None:
    mock_repo.write_file("justfile", "install:\n    uv sync\n")
    mock_repo.write_file("pyproject.toml", "[tool.ruff]\n")
    patched_justfile_apply.boost.apply()
    content = (mock_repo.path / "justfile").read_text()
    assert "install:" in content
    assert "format:" in content
    assert "lint: format" in content
    assert content.count("install:") == 1


def test_skips_when_all_recipes_already_present(
    mock_repo: RepositoryController,
    patched_justfile_apply: PatchedJustfileApply,
) -> None:
    mock_repo.write_file("pyproject.toml", "[tool.ruff]\n")
    existing = (
        "install:\n    uv sync\n\n"
        "format:\n    uv run ruff format\n\n"
        "lint: format\n    uv run ruff check\n\n"
        "check-ruff:\n    uv run ruff check\n"
    )
    mock_repo.write_file("justfile", existing)
    with pytest.raises(BoostSkipped):
        patched_justfile_apply.boost.apply()


def test_adds_run_var_when_not_defined_in_existing_justfile(
    mock_repo: RepositoryController,
    patched_justfile_apply: PatchedJustfileApply,
) -> None:
    mock_repo.write_file("justfile", "install:\n    uv sync\n")
    mock_repo.write_file("pyproject.toml", "[tool.ruff]\n")
    patched_justfile_apply.boost.apply()
    content = (mock_repo.path / "justfile").read_text()
    assert 'RUN := "uv run"' in content


def test_does_not_duplicate_run_var_if_already_defined(
    mock_repo: RepositoryController,
    patched_justfile_apply: PatchedJustfileApply,
) -> None:
    mock_repo.write_file("justfile", 'RUN := "uv run"\n\ninstall:\n    uv sync\n')
    mock_repo.write_file("pyproject.toml", "[tool.ruff]\n")
    patched_justfile_apply.boost.apply()
    content = (mock_repo.path / "justfile").read_text()
    assert content.count("RUN :=") == 1


def test_preserves_existing_justfile_content(
    mock_repo: RepositoryController,
    patched_justfile_apply: PatchedJustfileApply,
) -> None:
    mock_repo.write_file("justfile", "# My custom recipes\ntest:\n    pytest\n")
    mock_repo.write_file("pyproject.toml", "[project]\nname = 'test'\n")
    patched_justfile_apply.boost.apply()
    content = (mock_repo.path / "justfile").read_text()
    assert "# My custom recipes" in content
    assert "test:" in content
    assert "install:" in content


# =============================================================================
# RECIPE PARSING
# =============================================================================


def test_parses_simple_recipe_names(mock_repo: RepositoryController) -> None:
    mock_repo.write_file(
        "justfile",
        "install:\n    uv sync\n\nformat:\n    ruff format\n",
    )
    recipes = justfile_module._get_existing_recipes(mock_repo.path / "justfile")  # noqa: SLF001
    assert recipes == {"install", "format"}


def test_parses_recipe_with_dependencies(mock_repo: RepositoryController) -> None:
    mock_repo.write_file("justfile", "lint: format\n    ruff check\n")
    recipes = justfile_module._get_existing_recipes(mock_repo.path / "justfile")  # noqa: SLF001
    assert "lint" in recipes


def test_parses_recipe_with_args(mock_repo: RepositoryController) -> None:
    mock_repo.write_file("justfile", "test *args:\n    pytest {{ args }}\n")
    recipes = justfile_module._get_existing_recipes(mock_repo.path / "justfile")  # noqa: SLF001
    assert "test" in recipes


def test_does_not_parse_variable_assignment_as_recipe(mock_repo: RepositoryController) -> None:
    mock_repo.write_file("justfile", 'RUN := "uv run"\ninstall:\n    uv sync\n')
    recipes = justfile_module._get_existing_recipes(mock_repo.path / "justfile")  # noqa: SLF001
    assert "RUN" not in recipes
    assert "install" in recipes


# =============================================================================
# MISC
# =============================================================================


def test_commit_message(justfile_boost: JustfileBoost) -> None:
    assert justfile_boost.commit_message() == "✨ Add justfile with common commands"


def test_get_name() -> None:
    assert JustfileBoost.get_name() == "justfile"
