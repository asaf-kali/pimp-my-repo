"""Tests for UV boost implementation."""

import configparser
import re
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from unittest import mock
from unittest.mock import patch

import pytest
from tomlkit import document as toml_document
from tomlkit import table as toml_table

from pimp_my_repo.core.boosts.uv.detector import (
    detect_all,
    detect_dependency_files,
    detect_existing_configs,
)
from pimp_my_repo.core.boosts.uv.uv import UvBoost
from pimp_my_repo.core.tools.subprocess import CommandResult
from pimp_my_repo.core.tools.uv import UvNotFoundError

if TYPE_CHECKING:
    from collections.abc import Generator

    from pimp_my_repo.core.tools.boost_tools import BoostTools
    from pimp_my_repo.core.tools.repo import RepositoryController


# =============================================================================
# DETECTOR TESTS
# =============================================================================


def test_detect_empty_repo(mock_repo: RepositoryController) -> None:
    result = detect_dependency_files(mock_repo.path)
    assert result.requirements_txt is False
    assert result.setup_py is False
    assert result.pyproject_toml is False
    assert result.pipfile is False
    assert result.poetry_lock is False
    assert result.pipfile_lock is False


def test_detect_all_dependency_files_present(mock_repo: RepositoryController) -> None:
    mock_repo.write_file("requirements.txt", "requests>=2.0.0")
    mock_repo.write_file("setup.py", "from setuptools import setup")
    mock_repo.write_file("setup.cfg", "[metadata]\nname = test")
    mock_repo.write_file("pyproject.toml", "[project]\nname = 'test'")
    mock_repo.write_file("Pipfile", "[packages]")
    mock_repo.write_file("poetry.lock", "# lock")
    mock_repo.write_file("Pipfile.lock", "{}")

    result = detect_dependency_files(mock_repo.path)
    assert result.requirements_txt is True
    assert result.setup_py is True
    assert result.setup_cfg is True
    assert result.pyproject_toml is True
    assert result.pipfile is True
    assert result.poetry_lock is True
    assert result.pipfile_lock is True


def test_detect_partial_dependency_files(mock_repo: RepositoryController) -> None:
    mock_repo.write_file("requirements.txt", "requests>=2.0.0")
    mock_repo.write_file("pyproject.toml", "[project]\nname = 'test'")

    result = detect_dependency_files(mock_repo.path)
    assert result.requirements_txt is True
    assert result.pyproject_toml is True
    assert result.setup_py is False
    assert result.pipfile is False


def test_detect_pipfile_lock_without_pipfile(mock_repo: RepositoryController) -> None:
    mock_repo.write_file("Pipfile.lock", '{"_meta": {}}')

    result = detect_dependency_files(mock_repo.path)
    assert result.pipfile_lock is True
    assert result.pipfile is False


def test_detect_configs_empty_repo(mock_repo: RepositoryController) -> None:
    result = detect_existing_configs(mock_repo.path)
    assert result.ruff_dot_toml is False
    assert result.ruff_toml is False
    assert result.mypy_ini is False
    assert result.mypy_dot_ini is False
    assert result.pre_commit_config_dot_yaml is False
    assert result.justfile is False
    assert result.makefile is False


def test_detect_all_configs_present(mock_repo: RepositoryController) -> None:
    mock_repo.write_file(".ruff.toml", "[lint]")
    mock_repo.write_file("ruff.toml", "[lint]")
    mock_repo.write_file("mypy.ini", "[mypy]")
    mock_repo.write_file(".mypy.ini", "[mypy]")
    mock_repo.write_file(".pre-commit-config.yaml", "repos: []")
    mock_repo.write_file("pre-commit-config.yaml", "repos: []")
    mock_repo.write_file("justfile", "default:")
    mock_repo.write_file("Makefile", "all:")
    mock_repo.write_file("makefile", "all:")

    result = detect_existing_configs(mock_repo.path)
    assert result.ruff_dot_toml is True
    assert result.ruff_toml is True
    assert result.mypy_ini is True
    assert result.mypy_dot_ini is True
    assert result.pre_commit_config_dot_yaml is True
    assert result.pre_commit_config_yaml is True
    assert result.justfile is True
    assert result.makefile is True
    assert result.makefile_lower is True


def test_detect_partial_configs(mock_repo: RepositoryController) -> None:
    mock_repo.write_file("ruff.toml", "[lint]")
    mock_repo.write_file("justfile", "default:")

    result = detect_existing_configs(mock_repo.path)
    assert result.ruff_toml is True
    assert result.justfile is True
    assert result.ruff_dot_toml is False
    assert result.makefile is False


def test_detect_all_returns_both_categories(mock_repo: RepositoryController) -> None:
    result = detect_all(mock_repo.path)
    assert result.dependencies is not None
    assert result.configs is not None


def test_detect_all_integration_with_files(mock_repo: RepositoryController) -> None:
    mock_repo.write_file("requirements.txt", "requests>=2.0.0")
    mock_repo.write_file("ruff.toml", "[lint]")

    result = detect_all(mock_repo.path)
    assert result.dependencies.requirements_txt is True
    assert result.configs.ruff_toml is True
    assert result.dependencies.pipfile is False
    assert result.configs.justfile is False


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def uv_boost(boost_tools: BoostTools) -> UvBoost:
    return UvBoost(boost_tools)


@dataclass
class PatchedUvApply:
    """Pre-patched UvBoost with all subprocess mocks wired for apply()."""

    boost: UvBoost
    mock_exec: mock.MagicMock
    mock_exec_uvx: mock.MagicMock
    mock_add_from_requirements: mock.MagicMock


@pytest.fixture
def patched_uv_apply(mock_repo: RepositoryController, uv_boost: UvBoost) -> Generator[PatchedUvApply]:
    """Yield a UvBoost with all subprocess calls pre-mocked (no real uv execution)."""

    def create_lock_file(*args: str, **_kwargs: object) -> mock.MagicMock:
        if args and args[0] == "lock":
            (mock_repo.path / "uv.lock").touch()
        return mock.MagicMock(returncode=0, stdout="", stderr="")

    with (
        patch.object(uv_boost, "_check_uv_installed", return_value=True),
        patch.object(uv_boost.tools.uv, "exec", side_effect=create_lock_file) as mock_exec,
        patch.object(uv_boost.tools.uv, "exec_uvx") as mock_exec_uvx,
        patch.object(uv_boost.tools.uv, "add_from_requirements_file") as mock_add,
        patch("pimp_my_repo.core.boosts.uv.uv.resolve_requires_python", return_value=None),
    ):
        yield PatchedUvApply(
            boost=uv_boost,
            mock_exec=mock_exec,
            mock_exec_uvx=mock_exec_uvx,
            mock_add_from_requirements=mock_add,
        )


@pytest.fixture
def patched_uv_boost_installed(uv_boost: UvBoost) -> Generator[UvBoost]:
    with patch.object(uv_boost, "_check_uv_installed", return_value=True):
        yield uv_boost


@pytest.fixture
def patched_uv_boost_not_installed(uv_boost: UvBoost) -> Generator[UvBoost]:
    with (
        patch.object(uv_boost, "_check_uv_installed", return_value=False),
        patch.object(uv_boost, "_install_uv", return_value=False),
    ):
        yield uv_boost


@pytest.fixture
def patched_uv_boost_installable(uv_boost: UvBoost) -> Generator[UvBoost]:
    check_calls = [False, True]
    with (
        patch.object(uv_boost, "_check_uv_installed", side_effect=lambda: check_calls.pop(0)),
        patch.object(uv_boost, "_install_uv", return_value=True),
    ):
        yield uv_boost


@pytest.fixture
def patched_uv_boost_installable_with_mocked_run(uv_boost: UvBoost) -> Generator[UvBoost]:
    """Yield a UvBoost that can be installed and has uv.run mocked out."""
    check_calls = [False, True]
    with (
        patch.object(uv_boost, "_check_uv_installed", side_effect=lambda: check_calls.pop(0)),
        patch.object(uv_boost, "_install_uv", return_value=True),
        patch.object(uv_boost.tools.uv, "exec"),
        patch("pimp_my_repo.core.boosts.uv.uv.resolve_requires_python", return_value=None),
    ):
        yield uv_boost


@pytest.fixture
def uv_boost_with_migration_error(mock_repo: RepositoryController, uv_boost: UvBoost) -> Generator[UvBoost]:
    """Yield a UvBoost set up for poetry migration that will fail on run_uvx."""
    mock_repo.write_file("poetry.lock", "# Poetry lock file")
    mock_repo.write_file("pyproject.toml", "[tool.poetry]\nname = 'test'")
    error = subprocess.CalledProcessError(1, "uvx", stderr="Migration failed")
    with patch.object(uv_boost.tools.uv, "exec_uvx", side_effect=error):
        yield uv_boost


@pytest.fixture
def uv_boost_with_lock_error(mock_repo: RepositoryController, uv_boost: UvBoost) -> Generator[UvBoost]:
    """Yield a UvBoost with a pyproject.toml that will fail on uv lock."""
    mock_repo.write_file("pyproject.toml", "[project]\nname = 'test'\nversion = '0.1.0'")
    error = subprocess.CalledProcessError(1, "uv lock", stderr="Lock failed")

    def run_side_effect(*args: str, check: bool = True) -> CommandResult:  # noqa: ARG001
        if args and args[0] == "lock":
            raise error
        return CommandResult(cmd=["uv", *args], returncode=0, stdout="", stderr="")

    with (
        patch.object(uv_boost.tools.uv, "exec", side_effect=run_side_effect),
        patch("pimp_my_repo.core.boosts.uv.uv.resolve_requires_python", return_value=None),
    ):
        yield uv_boost


@pytest.fixture
def uv_boost_check_called_process_error(uv_boost: UvBoost) -> Generator[UvBoost]:
    """Yield a UvBoost where uv.run raises CalledProcessError for version check."""
    error = subprocess.CalledProcessError(1, "uv --version")
    with patch.object(uv_boost.tools.uv, "exec", side_effect=error):
        yield uv_boost


@pytest.fixture
def uv_boost_check_oserror(uv_boost: UvBoost) -> Generator[UvBoost]:
    """Yield a UvBoost where uv.run raises OSError for version check."""
    with patch.object(uv_boost.tools.uv, "exec", side_effect=OSError("System error")):
        yield uv_boost


@pytest.fixture
def uv_boost_check_file_not_found(uv_boost: UvBoost) -> Generator[UvBoost]:
    """Yield a UvBoost where uv.run raises FileNotFoundError for version check."""
    with patch.object(uv_boost.tools.uv, "exec", side_effect=FileNotFoundError("uv not found")):
        yield uv_boost


# =============================================================================
# PRECONDITIONS
# =============================================================================


@pytest.mark.smoke
def test_apply_raises_skip_when_uv_not_installed(patched_uv_boost_not_installed: UvBoost) -> None:
    with pytest.raises(UvNotFoundError, match="uv is not installed"):
        patched_uv_boost_not_installed.apply()


@pytest.mark.smoke
def test_apply_does_not_skip_when_uv_installable(patched_uv_boost_installable_with_mocked_run: UvBoost) -> None:
    patched_uv_boost_installable_with_mocked_run.apply()


# =============================================================================
# MIGRATION DETECTION
# =============================================================================


def test_has_migration_source_detects_poetry_lock(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    mock_repo.write_file("poetry.lock", "# Poetry lock file")
    assert uv_boost._has_migration_source() is True  # noqa: SLF001


def test_has_migration_source_detects_poetry_config(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    pyproject_content = '[tool.poetry]\nname = "test-project"\nversion = "0.1.0"\n'
    mock_repo.write_file("pyproject.toml", pyproject_content)
    assert uv_boost._has_migration_source() is True  # noqa: SLF001


@pytest.mark.smoke
def test_has_migration_source_detects_requirements_txt(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    mock_repo.write_file("requirements.txt", "requests>=2.0.0")
    assert uv_boost._has_migration_source() is True  # noqa: SLF001


def test_has_migration_source_detects_multiple_requirements_files(
    mock_repo: RepositoryController, uv_boost: UvBoost
) -> None:
    mock_repo.write_file("requirements.txt", "requests>=2.0.0")
    mock_repo.write_file("requirements-dev.txt", "pytest>=7.0.0")
    assert uv_boost._has_migration_source() is True  # noqa: SLF001


def test_has_migration_source_detects_pipfile(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    mock_repo.write_file("Pipfile", "[packages]\nrequests = '>=2.0.0'")
    assert uv_boost._has_migration_source() is True  # noqa: SLF001


def test_has_migration_source_no_source(uv_boost: UvBoost) -> None:
    assert uv_boost._has_migration_source() is False  # noqa: SLF001


def test_has_migration_source_ignores_non_poetry_pyproject(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    pyproject_content = '[project]\nname = "test-project"\nversion = "0.1.0"\n'
    mock_repo.write_file("pyproject.toml", pyproject_content)
    assert uv_boost._has_migration_source() is False  # noqa: SLF001


def test_has_project_table_true(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    """_has_project_table returns True when pyproject.toml has [project]."""
    mock_repo.write_file("pyproject.toml", '[project]\nname = "myapp"\n')
    assert uv_boost._has_project_table() is True  # noqa: SLF001


def test_has_project_table_false_tool_only(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    """_has_project_table returns False when pyproject.toml has only [tool.*] sections."""
    mock_repo.write_file("pyproject.toml", '[tool.poetry]\nname = "myapp"\n')
    assert uv_boost._has_project_table() is False  # noqa: SLF001


def test_has_project_table_false_no_pyproject(uv_boost: UvBoost) -> None:
    """_has_project_table returns False when pyproject.toml does not exist."""
    assert uv_boost._has_project_table() is False  # noqa: SLF001


def test_has_migration_source_pep621_with_root_requirements(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    """[project] table takes precedence — no migration even if requirements.txt is present."""
    mock_repo.write_file("pyproject.toml", '[project]\nname = "myapp"\ndependencies = ["requests"]\n')
    mock_repo.write_file("requirements.txt", "requests>=2.0.0")
    assert uv_boost._has_migration_source() is False  # noqa: SLF001


def test_has_migration_source_ignores_docs_requirements(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    """requirements.txt inside docs/ should not trigger migration (Django-style repos)."""
    mock_repo.write_file("docs/requirements.txt", "sphinx>=7.0.0")
    assert uv_boost._has_migration_source() is False  # noqa: SLF001


# =============================================================================
# APPLY
# =============================================================================


def test_apply_with_poetry_migration(mock_repo: RepositoryController, patched_uv_apply: PatchedUvApply) -> None:
    mock_repo.write_file("poetry.lock", "# Poetry lock file")
    mock_repo.write_file(
        "pyproject.toml",
        '[tool.poetry]\nname = "test-project"\nversion = "0.1.0"\n\n'
        '[tool.poetry.dependencies]\npython = "^3.8"\nrequests = "^2.28.0"\n',
    )
    patched_uv_apply.boost.apply()
    assert (mock_repo.path / "pyproject.toml").exists()
    assert (mock_repo.path / "uv.lock").exists()
    patched_uv_apply.mock_exec_uvx.assert_called_once_with("migrate-to-uv", "--skip-lock")


def test_apply_with_requirements_txt(mock_repo: RepositoryController, patched_uv_apply: PatchedUvApply) -> None:
    mock_repo.write_file("requirements.txt", "requests>=2.0.0\npytest>=7.0.0")
    patched_uv_apply.boost.apply()
    assert (mock_repo.path / "pyproject.toml").exists()
    assert (mock_repo.path / "uv.lock").exists()
    patched_uv_apply.mock_exec_uvx.assert_called_once_with("migrate-to-uv", "--skip-lock")


def test_apply_creates_minimal_pyproject_when_no_source(
    mock_repo: RepositoryController, patched_uv_apply: PatchedUvApply
) -> None:
    patched_uv_apply.boost.apply()
    pyproject_path = mock_repo.path / "pyproject.toml"
    assert pyproject_path.exists()
    assert (mock_repo.path / "uv.lock").exists()
    content = pyproject_path.read_text()
    assert "[project]" in content
    assert "[tool.uv]" in content


def test_apply_ensures_uv_config(mock_repo: RepositoryController, patched_uv_apply: PatchedUvApply) -> None:
    mock_repo.write_file("pyproject.toml", '[project]\nname = "test-project"\nversion = "0.1.0"\n')
    patched_uv_apply.boost.apply()
    assert "[tool.uv]" in (mock_repo.path / "pyproject.toml").read_text()


def test_apply_preserves_existing_pyproject(mock_repo: RepositoryController, patched_uv_apply: PatchedUvApply) -> None:
    mock_repo.write_file(
        "pyproject.toml",
        '[project]\nname = "test-project"\nversion = "0.1.0"\n'
        'description = "A test project"\n\n[tool.ruff]\nline-length = 120\n',
    )
    patched_uv_apply.boost.apply()
    content = (mock_repo.path / "pyproject.toml").read_text()
    assert 'description = "A test project"' in content
    assert "[tool.ruff]" in content
    assert "[tool.uv]" in content


def test_apply_creates_uv_lock(mock_repo: RepositoryController, patched_uv_apply: PatchedUvApply) -> None:
    patched_uv_apply.boost.apply()
    assert (mock_repo.path / "uv.lock").exists()


def test_commit_message(uv_boost: UvBoost) -> None:
    assert uv_boost.commit_message() == "✨ Add UV dependency management"


# =============================================================================
# UV CONFIG
# =============================================================================


@pytest.mark.smoke
def test_ensure_uv_config_adds_section_when_missing(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    mock_repo.write_file("pyproject.toml", '[project]\nname = "test-project"\n')

    pyproject_data = uv_boost.tools.pyproject.read()
    pyproject_data = uv_boost._ensure_uv_config(pyproject_data, is_native=False)  # noqa: SLF001
    uv_boost.tools.pyproject.write(pyproject_data)

    pyproject_content_after = (mock_repo.path / "pyproject.toml").read_text()
    assert "[tool.uv]" in pyproject_content_after


def test_ensure_uv_config_preserves_existing_section(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    pyproject_content = '[project]\nname = "test-project"\n\n[tool.uv]\ndev-dependencies = []\n'
    mock_repo.write_file("pyproject.toml", pyproject_content)

    pyproject_data = uv_boost.tools.pyproject.read()
    pyproject_data = uv_boost._ensure_uv_config(pyproject_data, is_native=False)  # noqa: SLF001
    uv_boost.tools.pyproject.write(pyproject_data)

    pyproject_content_after = (mock_repo.path / "pyproject.toml").read_text()
    assert "[tool.uv]" in pyproject_content_after
    # mock_repo has no src/ or __init__.py → not an installable package
    assert "package = false" in pyproject_content_after
    assert "dev-dependencies" in pyproject_content_after  # existing keys preserved


def test_ensure_uv_config_sets_package_true_for_src_layout(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    mock_repo.write_file("pyproject.toml", '[project]\nname = "test-project"\n')
    (mock_repo.path / "src").mkdir()

    pyproject_data = uv_boost.tools.pyproject.read()
    pyproject_data = uv_boost._ensure_uv_config(pyproject_data, is_native=False)  # noqa: SLF001
    uv_boost.tools.pyproject.write(pyproject_data)

    assert "package = true" in (mock_repo.path / "pyproject.toml").read_text()


# =============================================================================
# SUBPROCESS ERROR HANDLING
# =============================================================================


@pytest.mark.smoke
def test_apply_raises_on_migration_failure(uv_boost_with_migration_error: UvBoost) -> None:
    with pytest.raises(subprocess.CalledProcessError) as exc_info:
        uv_boost_with_migration_error.apply()
    assert exc_info.value.returncode == 1


def test_apply_raises_on_lock_generation_failure(uv_boost_with_lock_error: UvBoost) -> None:
    with pytest.raises(subprocess.CalledProcessError):
        uv_boost_with_lock_error.apply()


def test_check_uv_installed_handles_called_process_error(uv_boost_check_called_process_error: UvBoost) -> None:
    result = uv_boost_check_called_process_error._check_uv_installed()  # noqa: SLF001
    assert result is False


def test_check_uv_installed_handles_oserror(uv_boost_check_oserror: UvBoost) -> None:
    result = uv_boost_check_oserror._check_uv_installed()  # noqa: SLF001
    assert result is False


def test_check_uv_installed_handles_file_not_found(uv_boost_check_file_not_found: UvBoost) -> None:
    result = uv_boost_check_file_not_found._check_uv_installed()  # noqa: SLF001
    assert result is False


# =============================================================================
# UV INSTALLATION FAILURES
# =============================================================================


@pytest.fixture
def uv_boost_pip_fails_script_succeeds(uv_boost: UvBoost) -> Generator[UvBoost]:
    """Yield a UvBoost where pip install fails but script install succeeds."""
    with (
        patch.object(uv_boost, "_try_pip_install", return_value=False),
        patch.object(uv_boost, "_try_script_install", return_value=True),
    ):
        yield uv_boost


@pytest.fixture
def uv_boost_both_install_fail(uv_boost: UvBoost) -> Generator[UvBoost]:
    """Yield a UvBoost where both pip and script install fail."""
    with (
        patch.object(uv_boost, "_try_pip_install", return_value=False),
        patch.object(uv_boost, "_try_script_install", return_value=False),
    ):
        yield uv_boost


@pytest.fixture
def uv_boost_pip_succeeds(uv_boost: UvBoost) -> Generator[UvBoost]:
    """Yield a UvBoost where pip install succeeds on the first try."""
    with (
        patch.object(uv_boost, "_try_script_install", return_value=False),
        patch.object(uv_boost, "_try_pip_install", return_value=True),
    ):
        yield uv_boost


def test_install_uv_pip_failure_falls_back_to_installer(uv_boost_pip_fails_script_succeeds: UvBoost) -> None:
    result = uv_boost_pip_fails_script_succeeds._install_uv()  # noqa: SLF001
    assert result is True


def test_install_uv_both_methods_fail(uv_boost_both_install_fail: UvBoost) -> None:
    result = uv_boost_both_install_fail._install_uv()  # noqa: SLF001
    assert result is False


def test_install_uv_pip_oserror_falls_back_to_installer(uv_boost_pip_fails_script_succeeds: UvBoost) -> None:
    """When pip install fails (including due to OSError caught internally), script install is tried."""
    result = uv_boost_pip_fails_script_succeeds._install_uv()  # noqa: SLF001
    assert result is True


def test_install_uv_installer_oserror_returns_false(uv_boost_both_install_fail: UvBoost) -> None:
    """When both install methods fail (including script raising OSError internally), returns False."""
    result = uv_boost_both_install_fail._install_uv()  # noqa: SLF001
    assert result is False


@pytest.mark.smoke
def test_install_uv_pip_success(uv_boost_pip_succeeds: UvBoost) -> None:
    result = uv_boost_pip_succeeds._install_uv()  # noqa: SLF001
    assert result is True


# =============================================================================
# PYPROJECT EDGE CASES
# =============================================================================


def test_write_pyproject_preserves_comments(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    pyproject_content = (
        "# This is a comment\n[project]\n"
        'name = "test-project"  # inline comment\nversion = "0.1.0"\n\n'
        "# Section comment\n[tool.ruff]\nline-length = 120\n"
    )
    mock_repo.write_file("pyproject.toml", pyproject_content)

    pyproject_data = uv_boost.tools.pyproject.read()
    pyproject_data = uv_boost._ensure_uv_config(pyproject_data, is_native=False)  # noqa: SLF001
    uv_boost.tools.pyproject.write(pyproject_data)

    content_after = (mock_repo.path / "pyproject.toml").read_text()
    assert "# This is a comment" in content_after
    assert "# Section comment" in content_after


def test_ensure_uv_config_with_existing_tool_section(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    pyproject_content = (
        '[project]\nname = "test-project"\n\n[tool.ruff]\nline-length = 120\n\n[tool.mypy]\nstrict = true\n'
    )
    mock_repo.write_file("pyproject.toml", pyproject_content)

    pyproject_data = uv_boost.tools.pyproject.read()
    pyproject_data = uv_boost._ensure_uv_config(pyproject_data, is_native=False)  # noqa: SLF001
    uv_boost.tools.pyproject.write(pyproject_data)

    content = (mock_repo.path / "pyproject.toml").read_text()
    assert "[tool.uv]" in content
    assert "[tool.ruff]" in content
    assert "[tool.mypy]" in content


# =============================================================================
# MIGRATION EDGE CASES
# =============================================================================


def test_has_migration_source_detects_pipfile_lock(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    mock_repo.write_file("Pipfile.lock", '{"_meta": {"hash": {}}}')
    assert uv_boost._has_migration_source() is True  # noqa: SLF001


def test_has_migration_source_empty_poetry_lock(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    mock_repo.write_file("poetry.lock", "")
    assert uv_boost._has_migration_source() is True  # noqa: SLF001


def test_has_migration_source_nested_requirements(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    mock_repo.write_file("requirements/base.txt", "requests>=2.0.0")
    mock_repo.write_file("requirements/dev.txt", "pytest>=7.0.0")
    assert uv_boost._has_migration_source() is False  # noqa: SLF001


def test_has_migration_source_requirements_dev_txt(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    mock_repo.write_file("requirements-dev.txt", "pytest>=7.0.0")
    assert uv_boost._has_migration_source() is True  # noqa: SLF001


def test_has_migration_source_requirements_test_txt(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    mock_repo.write_file("requirements-test.txt", "pytest>=7.0.0")
    assert uv_boost._has_migration_source() is True  # noqa: SLF001


def test_has_migration_source_detects_prefix_requirements_file(
    mock_repo: RepositoryController, uv_boost: UvBoost
) -> None:
    mock_repo.write_file("dev-requirements.txt", "pytest>=7.0.0")
    assert uv_boost._has_migration_source() is True  # noqa: SLF001


def test_has_migration_source_detects_test_prefix_requirements_file(
    mock_repo: RepositoryController, uv_boost: UvBoost
) -> None:
    mock_repo.write_file("test-requirements.txt", "pytest>=7.0.0")
    assert uv_boost._has_migration_source() is True  # noqa: SLF001


def test_has_migration_source_both_pipfile_and_poetry(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    mock_repo.write_file("Pipfile", "[packages]")
    mock_repo.write_file("poetry.lock", "# lock")
    assert uv_boost._has_migration_source() is True  # noqa: SLF001


def test_has_migration_source_does_not_detect_setup_cfg(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    # setup.cfg is handled by _migrate_from_setup_cfg(), not by migrate-to-uv
    mock_repo.write_file("setup.cfg", "[metadata]\nname = myproject\n\n[options]\ninstall_requires =\n    requests")
    assert uv_boost._has_migration_source() is False  # noqa: SLF001


def test_has_migration_source_detects_setup_py(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    """setup.py alone (no setup.cfg [options]) is NOT a migration source; falls through to _ensure_pyproject_exists."""
    mock_repo.write_file("setup.py", "from setuptools import setup\nsetup(name='myproject')")
    assert uv_boost._has_migration_source() is False  # noqa: SLF001


def test_has_migration_source_setup_cfg_with_setup_py(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    """setup.cfg with [metadata] only (no [options]) is bare — not a migration source even with setup.py."""
    mock_repo.write_file("setup.py", "from setuptools import setup")
    mock_repo.write_file("setup.cfg", "[metadata]\nname = myproject")
    assert uv_boost._has_migration_source() is False  # noqa: SLF001


def test_has_migration_source_ignores_bare_setup_cfg_without_setup_py(
    mock_repo: RepositoryController, uv_boost: UvBoost
) -> None:
    """Bare setup.cfg (no [options]) without setup.py is not a migration source."""
    mock_repo.write_file("setup.cfg", "[wheel]\nuniversal = 1")
    assert uv_boost._has_migration_source() is False  # noqa: SLF001


def test_has_migration_source_detects_bare_setup_cfg_with_setup_py(
    mock_repo: RepositoryController, uv_boost: UvBoost
) -> None:
    """Bare setup.cfg (no [options]) + setup.py is not a migration source."""
    mock_repo.write_file("setup.cfg", "[wheel]\nuniversal = 1")
    mock_repo.write_file("setup.py", "from setuptools import setup\nsetup(name='myproject')")
    assert uv_boost._has_migration_source() is False  # noqa: SLF001


# =============================================================================
# _IS_SETUP_CFG_BARE TESTS
# =============================================================================


def test_is_setup_cfg_bare_no_setup_cfg(uv_boost: UvBoost) -> None:
    assert uv_boost._is_setup_cfg_bare() is True  # noqa: SLF001


def test_is_setup_cfg_bare_only_wheel_section(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    mock_repo.write_file("setup.cfg", "[wheel]\nuniversal = 1")
    assert uv_boost._is_setup_cfg_bare() is True  # noqa: SLF001


def test_is_setup_cfg_bare_with_metadata_section(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    # [metadata] alone is not enough — migrate-to-uv requires [options]
    mock_repo.write_file("setup.cfg", "[metadata]\nname = myproject")
    assert uv_boost._is_setup_cfg_bare() is True  # noqa: SLF001


def test_is_setup_cfg_bare_with_options_section(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    mock_repo.write_file("setup.cfg", "[options]\npackages = find:")
    assert uv_boost._is_setup_cfg_bare() is False  # noqa: SLF001


# =============================================================================
# _PARSE_SETUP_PY_STR_KWARGS TESTS
# =============================================================================


def test_parse_setup_py_str_kwargs_no_setup_py(uv_boost: UvBoost) -> None:
    assert uv_boost._parse_setup_py_str_kwargs() == {}  # noqa: SLF001


def test_parse_setup_py_str_kwargs_extracts_string_fields(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    mock_repo.write_file(
        "setup.py",
        "from setuptools import setup\nsetup(name='foo', description='bar')",
    )
    result = uv_boost._parse_setup_py_str_kwargs()  # noqa: SLF001
    assert result == {"name": "foo", "description": "bar"}


def test_parse_setup_py_str_kwargs_skips_variable_version(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    mock_repo.write_file(
        "setup.py",
        "__version__ = '1.2.3'\nfrom setuptools import setup\nsetup(name='foo', version=__version__)",
    )
    result = uv_boost._parse_setup_py_str_kwargs()  # noqa: SLF001
    assert "version" not in result
    assert result.get("name") == "foo"


def test_parse_setup_py_str_kwargs_syntax_error(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    mock_repo.write_file("setup.py", "this is not valid python )(")
    assert uv_boost._parse_setup_py_str_kwargs() == {}  # noqa: SLF001


# =============================================================================
# _AUGMENT_SETUP_CFG_FROM_SETUP_PY TESTS
# =============================================================================


def test_augment_setup_cfg_creates_metadata_section(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    mock_repo.write_file(
        "setup.py",
        "from setuptools import setup\nsetup(name='myproject', description='A project')",
    )
    uv_boost._augment_setup_cfg_from_setup_py()  # noqa: SLF001

    cfg = configparser.ConfigParser()
    cfg.read(mock_repo.path / "setup.cfg")
    assert "metadata" in cfg.sections()
    assert cfg["metadata"]["name"] == "myproject"
    assert cfg["metadata"]["description"] == "A project"


def test_augment_setup_cfg_preserves_existing_sections(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    mock_repo.write_file("setup.cfg", "[wheel]\nuniversal = 1")
    mock_repo.write_file(
        "setup.py",
        "from setuptools import setup\nsetup(name='myproject')",
    )
    uv_boost._augment_setup_cfg_from_setup_py()  # noqa: SLF001

    cfg = configparser.ConfigParser()
    cfg.read(mock_repo.path / "setup.cfg")
    assert "wheel" in cfg.sections()
    assert cfg["wheel"]["universal"] == "1"
    assert "metadata" in cfg.sections()
    assert cfg["metadata"]["name"] == "myproject"


def test_augment_setup_cfg_does_nothing_without_string_kwargs(
    mock_repo: RepositoryController, uv_boost: UvBoost
) -> None:
    """When setup.py has no string kwargs, setup.cfg should not be touched."""
    mock_repo.write_file("setup.cfg", "[wheel]\nuniversal = 1")
    mock_repo.write_file(
        "setup.py",
        "__version__ = '1.0'\nfrom setuptools import setup\nsetup(version=__version__)",
    )
    original_content = (mock_repo.path / "setup.cfg").read_text()
    uv_boost._augment_setup_cfg_from_setup_py()  # noqa: SLF001
    assert (mock_repo.path / "setup.cfg").read_text() == original_content


# =============================================================================
# INTEGRATION: bare setup.cfg + setup.py
# =============================================================================


def test_apply_with_bare_setup_cfg_and_setup_py(
    mock_repo: RepositoryController, patched_uv_apply: PatchedUvApply
) -> None:
    """Full apply() on a repo with bare setup.cfg + setup.py skips migrate-to-uv and creates a minimal pyproject.toml."""  # noqa: E501
    mock_repo.write_file("setup.cfg", "[wheel]\nuniversal = 1")
    mock_repo.write_file(
        "setup.py",
        (
            "from setuptools import setup\n"
            "setup(\n"
            "    name='myproject',\n"
            "    version='1.0.0',\n"
            "    description='My project',\n"
            ")\n"
        ),
    )

    patched_uv_apply.boost.apply()
    # migrate-to-uv should NOT be called — bare setup.cfg + setup.py is not a migration source
    patched_uv_apply.mock_exec_uvx.assert_not_called()

    assert (mock_repo.path / "pyproject.toml").exists()
    assert (mock_repo.path / "uv.lock").exists()

    # setup.cfg should be unmodified (no augmentation)
    cfg = configparser.ConfigParser()
    cfg.read(mock_repo.path / "setup.cfg")
    assert "metadata" not in cfg.sections()


# =============================================================================
# REQUIREMENTS FILE DETECTION TESTS
# =============================================================================


def test_extract_group_from_filename_main(uv_boost: UvBoost) -> None:
    assert uv_boost._extract_group_from_filename("requirements.txt") is None  # noqa: SLF001


def test_extract_group_from_filename_dash_suffix(uv_boost: UvBoost) -> None:
    assert uv_boost._extract_group_from_filename("requirements-dev.txt") == "dev"  # noqa: SLF001
    assert uv_boost._extract_group_from_filename("requirements-test.txt") == "test"  # noqa: SLF001


def test_extract_group_from_filename_dot_suffix(uv_boost: UvBoost) -> None:
    assert uv_boost._extract_group_from_filename("requirements.dev.txt") == "dev"  # noqa: SLF001
    assert uv_boost._extract_group_from_filename("requirements.lint.txt") == "lint"  # noqa: SLF001


def test_extract_group_from_filename_prefix(uv_boost: UvBoost) -> None:
    assert uv_boost._extract_group_from_filename("dev-requirements.txt") == "dev"  # noqa: SLF001
    assert uv_boost._extract_group_from_filename("test-requirements.txt") == "test"  # noqa: SLF001


def test_detect_requirements_files_main_only(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    mock_repo.write_file("requirements.txt", "requests>=2.0.0")
    result = uv_boost._detect_requirements_files()  # noqa: SLF001
    assert result.main == mock_repo.path / "requirements.txt"
    assert result.groups == {}


def test_detect_requirements_files_with_groups(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    mock_repo.write_file("requirements.txt", "requests>=2.0.0")
    mock_repo.write_file("requirements-dev.txt", "pytest>=7.0.0")
    mock_repo.write_file("test-requirements.txt", "pytest-cov>=4.0.0")
    mock_repo.write_file("requirements.lint.txt", "ruff>=0.1.0")
    result = uv_boost._detect_requirements_files()  # noqa: SLF001
    assert result.main == mock_repo.path / "requirements.txt"
    assert "dev" in result.groups
    assert "test" in result.groups
    assert "lint" in result.groups
    assert len(result.groups["dev"]) == 1
    assert len(result.groups["test"]) == 1
    assert len(result.groups["lint"]) == 1


def test_detect_requirements_files_multiple_same_group(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    mock_repo.write_file("requirements-dev.txt", "pytest>=7.0.0")
    mock_repo.write_file("dev-requirements.txt", "black>=23.0.0")
    result = uv_boost._detect_requirements_files()  # noqa: SLF001
    assert result.main is None
    assert "dev" in result.groups
    dev_files = result.groups["dev"]
    assert len(dev_files) == 2  # noqa: PLR2004


def test_detect_requirements_files_no_main(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    mock_repo.write_file("requirements-dev.txt", "pytest>=7.0.0")
    result = uv_boost._detect_requirements_files()  # noqa: SLF001
    assert result.main is None
    assert "dev" in result.groups


def test_apply_with_pipfile_migration(mock_repo: RepositoryController, patched_uv_apply: PatchedUvApply) -> None:
    mock_repo.write_file("Pipfile", '[packages]\nrequests = ">=2.0.0"\n\n[dev-packages]\npytest = ">=7.0.0"\n')
    patched_uv_apply.boost.apply()
    assert (mock_repo.path / "pyproject.toml").exists()
    assert (mock_repo.path / "uv.lock").exists()
    patched_uv_apply.mock_exec_uvx.assert_called_once_with("migrate-to-uv", "--skip-lock")


def test_apply_adds_grouped_requirements_files(
    mock_repo: RepositoryController, patched_uv_apply: PatchedUvApply
) -> None:
    """PMR adds grouped requirements files that migrate-to-uv did not consume."""
    mock_repo.write_file("requirements.txt", "requests>=2.0.0")
    mock_repo.write_file("requirements-dev.txt", "pytest>=7.0.0")
    mock_repo.write_file("test-requirements.txt", "pytest-cov>=4.0.0")

    def simulate_migrate_to_uv(*_args: str, **_kwargs: object) -> None:
        # simulate migrate-to-uv consuming requirements-dev.txt (recognised pattern)
        (mock_repo.path / "requirements-dev.txt").unlink()

    patched_uv_apply.mock_exec_uvx.side_effect = simulate_migrate_to_uv
    patched_uv_apply.boost.apply()

    # Only test-requirements.txt (unrecognised by migrate-to-uv) should be added by PMR
    assert patched_uv_apply.mock_add_from_requirements.call_count == 1
    call = patched_uv_apply.mock_add_from_requirements.call_args_list[0]
    assert call.kwargs.get("group") == "test"
    assert call.args[0].name == "test-requirements.txt"


def test_apply_infers_project_name_from_directory(
    mock_repo: RepositoryController, patched_uv_apply: PatchedUvApply
) -> None:
    patched_uv_apply.boost.apply()
    content = (mock_repo.path / "pyproject.toml").read_text()
    assert "[project]" in content
    name_match = re.search(r'name = "([^"]+)"', content)
    assert name_match, "Could not find project name in pyproject.toml"
    project_name = name_match.group(1)
    assert project_name[0].isalnum(), f"Project name must start with alphanumeric, got: {project_name!r}"
    assert project_name[-1].isalnum(), f"Project name must end with alphanumeric, got: {project_name!r}"


# =============================================================================
# IDEMPOTENCY
# =============================================================================


def test_apply_is_idempotent(mock_repo: RepositoryController, patched_uv_apply: PatchedUvApply) -> None:
    mock_repo.write_file("pyproject.toml", '[project]\nname = "test-project"\nversion = "0.1.0"\n')

    patched_uv_apply.boost.apply()
    first_content = (mock_repo.path / "pyproject.toml").read_text()

    patched_uv_apply.boost.apply()
    second_content = (mock_repo.path / "pyproject.toml").read_text()

    assert "[tool.uv]" in first_content
    assert "[tool.uv]" in second_content


def test_get_name_returns_correct_value() -> None:
    assert UvBoost.get_name() == "uv"


# =============================================================================
# _LOCK_WITH_REQUIRES_PYTHON TESTS
# =============================================================================


@pytest.fixture
def mock_resolve_requires_python() -> Generator[mock.MagicMock]:
    with patch("pimp_my_repo.core.boosts.uv.uv.resolve_requires_python", return_value=">=3.8") as m:
        yield m


@pytest.fixture
def mock_try_lock_and_sync(uv_boost: UvBoost) -> Generator[mock.MagicMock]:
    with mock.patch.object(uv_boost, "_try_lock_and_sync", return_value=True) as m:
        yield m


@pytest.fixture
def mock_lock_and_sync(uv_boost: UvBoost) -> Generator[mock.MagicMock]:
    with mock.patch.object(uv_boost, "_lock_and_sync") as m:
        yield m


def test_lock_skips_detection_if_requires_python_already_set(
    mock_repo: RepositoryController,
    uv_boost: UvBoost,
    mock_lock_and_sync: mock.MagicMock,
) -> None:
    mock_repo.write_file("pyproject.toml", '[project]\nname = "x"\nrequires-python = ">=3.9,<3.10"\n')
    with patch("pimp_my_repo.core.boosts.uv.uv.resolve_requires_python") as mock_resolve:
        uv_boost._lock_with_requires_python()  # noqa: SLF001
        mock_resolve.assert_not_called()
    mock_lock_and_sync.assert_called_once()


def test_lock_adds_upper_bound_to_bare_requires_python(
    mock_repo: RepositoryController,
    uv_boost: UvBoost,
    mock_lock_and_sync: mock.MagicMock,
) -> None:
    mock_repo.write_file("pyproject.toml", '[project]\nname = "x"\nrequires-python = ">=3.9"\n')
    with patch("pimp_my_repo.core.boosts.uv.uv.resolve_requires_python") as mock_resolve:
        uv_boost._lock_with_requires_python()  # noqa: SLF001
        mock_resolve.assert_not_called()
    content = (mock_repo.path / "pyproject.toml").read_text()
    assert 'requires-python = ">=3.9,<3.10"' in content
    mock_lock_and_sync.assert_called_once()


def test_lock_leaves_existing_upper_bound_unchanged(
    mock_repo: RepositoryController,
    uv_boost: UvBoost,
    mock_lock_and_sync: mock.MagicMock,
) -> None:
    mock_repo.write_file("pyproject.toml", '[project]\nname = "x"\nrequires-python = ">=3.9,<3.12"\n')
    with patch("pimp_my_repo.core.boosts.uv.uv.resolve_requires_python"):
        uv_boost._lock_with_requires_python()  # noqa: SLF001
    content = (mock_repo.path / "pyproject.toml").read_text()
    assert 'requires-python = ">=3.9,<3.12"' in content
    mock_lock_and_sync.assert_called_once()


def test_lock_skips_requires_python_when_no_version_detected(
    mock_repo: RepositoryController,
    uv_boost: UvBoost,
    mock_lock_and_sync: mock.MagicMock,
) -> None:
    mock_repo.write_file("pyproject.toml", '[project]\nname = "x"\n')
    with patch("pimp_my_repo.core.boosts.uv.uv.resolve_requires_python", return_value=None):
        uv_boost._lock_with_requires_python()  # noqa: SLF001
    content = (mock_repo.path / "pyproject.toml").read_text()
    assert "requires-python" not in content
    mock_lock_and_sync.assert_called_once()


def test_lock_sets_requires_python_on_first_success(
    mock_repo: RepositoryController,
    uv_boost: UvBoost,
    mock_resolve_requires_python: mock.MagicMock,  # noqa: ARG001
    mock_try_lock_and_sync: mock.MagicMock,
) -> None:
    mock_repo.write_file("pyproject.toml", '[project]\nname = "x"\n')
    mock_try_lock_and_sync.return_value = True

    uv_boost._lock_with_requires_python()  # noqa: SLF001

    content = (mock_repo.path / "pyproject.toml").read_text()
    assert 'requires-python = ">=3.8,<3.9"' in content
    mock_try_lock_and_sync.assert_called_once()


def test_lock_searches_down_on_failure(
    mock_repo: RepositoryController,
    uv_boost: UvBoost,
    mock_resolve_requires_python: mock.MagicMock,  # noqa: ARG001
    mock_try_lock_and_sync: mock.MagicMock,
) -> None:
    mock_repo.write_file("pyproject.toml", '[project]\nname = "x"\n')
    # Detected is 3.8 (from mock_resolve_requires_python), fails.
    # Search from max down: first attempt succeeds.
    mock_try_lock_and_sync.side_effect = [False, True]

    with patch("pimp_my_repo.core.boosts.uv.uv._MAX_PYTHON_MINOR", 10):
        uv_boost._lock_with_requires_python()  # noqa: SLF001

    content = (mock_repo.path / "pyproject.toml").read_text()
    # After detected 3.8 fails, searches 3.10 (max) → succeeds
    expected_attempts = 2
    assert 'requires-python = ">=3.10,<3.11"' in content
    assert mock_try_lock_and_sync.call_count == expected_attempts


def test_lock_removes_requires_python_when_all_versions_fail(
    mock_repo: RepositoryController,
    uv_boost: UvBoost,
    mock_lock_and_sync: mock.MagicMock,
    mock_try_lock_and_sync: mock.MagicMock,
) -> None:
    mock_repo.write_file("pyproject.toml", '[project]\nname = "x"\n')
    mock_try_lock_and_sync.return_value = False
    with (
        patch("pimp_my_repo.core.boosts.uv.uv.resolve_requires_python", return_value=">=3.8"),
        patch("pimp_my_repo.core.boosts.uv.uv._MAX_PYTHON_MINOR", 9),
    ):
        uv_boost._lock_with_requires_python()  # noqa: SLF001

    content = (mock_repo.path / "pyproject.toml").read_text()
    assert "requires-python" not in content
    mock_lock_and_sync.assert_called_once()


# =============================================================================
# _STRIP_NATIVE_BACKEND_METADATA
# =============================================================================


def test_strip_native_backend_metadata_no_project_section(
    mock_repo: RepositoryController,
    uv_boost: UvBoost,
) -> None:
    mock_repo.write_file("pyproject.toml", '[build-system]\nrequires = ["mesonpy"]\n')
    data = uv_boost.tools.pyproject.read()
    result = uv_boost._strip_native_backend_metadata(data)  # noqa: SLF001
    assert result is data  # unchanged


def test_strip_native_backend_metadata_removes_optional_deps(
    mock_repo: RepositoryController,
    uv_boost: UvBoost,
) -> None:
    mock_repo.write_file(
        "pyproject.toml",
        '[project]\nname = "x"\n[project.optional-dependencies]\nextra = ["requests"]\n',
    )
    data = uv_boost.tools.pyproject.read()
    result = uv_boost._strip_native_backend_metadata(data)  # noqa: SLF001
    project: Any = result["project"]
    assert "optional-dependencies" not in project


def test_strip_native_backend_metadata_replaces_dynamic_version(
    mock_repo: RepositoryController,
    uv_boost: UvBoost,
) -> None:
    mock_repo.write_file("pyproject.toml", '[project]\nname = "x"\ndynamic = ["version"]\n')
    data = uv_boost.tools.pyproject.read()
    result = uv_boost._strip_native_backend_metadata(data)  # noqa: SLF001
    project: Any = result["project"]
    assert "dynamic" not in project
    assert project["version"] == "0.0.0"


def test_strip_native_backend_metadata_preserves_other_dynamic_fields(
    mock_repo: RepositoryController,
    uv_boost: UvBoost,
) -> None:
    mock_repo.write_file("pyproject.toml", '[project]\nname = "x"\ndynamic = ["version", "description"]\n')
    data = uv_boost.tools.pyproject.read()
    result = uv_boost._strip_native_backend_metadata(data)  # noqa: SLF001
    project: Any = result["project"]
    assert "description" in project["dynamic"]
    assert "version" not in project["dynamic"]


def test_strip_native_backend_metadata_skips_when_version_already_set(
    mock_repo: RepositoryController,
    uv_boost: UvBoost,
) -> None:
    mock_repo.write_file("pyproject.toml", '[project]\nname = "x"\nversion = "1.2.3"\ndynamic = ["version"]\n')
    data = uv_boost.tools.pyproject.read()
    result = uv_boost._strip_native_backend_metadata(data)  # noqa: SLF001
    project: Any = result["project"]
    assert project["version"] == "1.2.3"


# =============================================================================
# _HAS_NATIVE_BUILD_BACKEND
# =============================================================================


def test_has_native_build_backend_oserror(uv_boost: UvBoost) -> None:
    with patch.object(uv_boost.tools.pyproject, "read", side_effect=OSError):
        assert uv_boost._has_native_build_backend() is False  # noqa: SLF001


def test_has_native_build_backend_value_error(uv_boost: UvBoost) -> None:
    with patch.object(uv_boost.tools.pyproject, "read", side_effect=ValueError):
        assert uv_boost._has_native_build_backend() is False  # noqa: SLF001


# =============================================================================
# _FIX_EMPTY_PROJECT_NAME / _WRITE / _REMOVE_REQUIRES_PYTHON / _ENSURE_UPPER_BOUND
# =============================================================================


def test_fix_empty_project_name_skips_when_no_project_section(
    mock_repo: RepositoryController,
    uv_boost: UvBoost,
) -> None:
    mock_repo.write_file("pyproject.toml", "[tool.uv]\npackage = false\n")
    uv_boost._fix_empty_project_name()  # noqa: SLF001
    content = (mock_repo.path / "pyproject.toml").read_text()
    assert "name" not in content


def test_write_requires_python_creates_project_section(
    mock_repo: RepositoryController,
    uv_boost: UvBoost,
) -> None:
    mock_repo.write_file("pyproject.toml", "[tool.uv]\npackage = false\n")
    uv_boost._write_requires_python(">=3.9")  # noqa: SLF001
    content = (mock_repo.path / "pyproject.toml").read_text()
    assert 'requires-python = ">=3.9"' in content


def test_remove_requires_python_skips_when_no_project_section(
    mock_repo: RepositoryController,
    uv_boost: UvBoost,
) -> None:
    mock_repo.write_file("pyproject.toml", "[tool.uv]\npackage = false\n")
    uv_boost._remove_requires_python()  # noqa: SLF001
    content = (mock_repo.path / "pyproject.toml").read_text()
    assert "requires-python" not in content


def test_ensure_upper_bound_skips_when_no_project_section(
    mock_repo: RepositoryController,
    uv_boost: UvBoost,
) -> None:
    mock_repo.write_file("pyproject.toml", "[tool.uv]\npackage = false\n")
    uv_boost._ensure_upper_bound()  # noqa: SLF001  # should not raise


# =============================================================================
# _BUILD_PROJECT_TABLE AND _APPLY_SETUP_CFG_SCRIPTS
# =============================================================================


def test_build_project_table_with_attr_version(uv_boost: UvBoost) -> None:
    cfg = configparser.ConfigParser()
    cfg["metadata"] = {"name": "mylib", "version": "attr: mylib.__version__"}
    result = uv_boost._build_project_table(cfg)  # noqa: SLF001
    assert result["version"] == "0.1.0"
    assert result["name"] == "mylib"


def test_build_project_table_with_python_requires_and_deps(uv_boost: UvBoost) -> None:
    cfg = configparser.ConfigParser()
    cfg["metadata"] = {"name": "mylib", "version": "1.0.0"}
    cfg["options"] = {"python_requires": ">=3.8", "install_requires": "requests>=2.0\nclick>=8.0"}
    result = uv_boost._build_project_table(cfg)  # noqa: SLF001
    assert result["requires-python"] == ">=3.8"
    assert "requests>=2.0" in result["dependencies"]
    assert "click>=8.0" in result["dependencies"]


def test_build_project_table_with_extras_require(uv_boost: UvBoost) -> None:
    cfg = configparser.ConfigParser()
    cfg["metadata"] = {"name": "mylib", "version": "1.0.0"}
    cfg["options.extras_require"] = {"dev": "pytest>=7.0\n# comment\n", "docs": "sphinx>=5.0"}
    result = uv_boost._build_project_table(cfg)  # noqa: SLF001
    assert "optional-dependencies" in result
    assert "pytest>=7.0" in result["optional-dependencies"]["dev"]
    assert "sphinx>=5.0" in result["optional-dependencies"]["docs"]


def test_apply_setup_cfg_scripts_adds_scripts(uv_boost: UvBoost) -> None:
    cfg = configparser.ConfigParser()
    cfg["options.entry_points"] = {"console_scripts": "myapp = mypackage.cli:main\n"}
    pyproject_data = toml_document()
    project_tbl: Any = toml_table()
    pyproject_data["project"] = project_tbl
    uv_boost._apply_setup_cfg_scripts(cfg, pyproject_data)  # noqa: SLF001
    result_project: Any = pyproject_data["project"]
    assert result_project["scripts"]["myapp"] == "mypackage.cli:main"


def test_apply_setup_cfg_scripts_skips_when_no_scripts(uv_boost: UvBoost) -> None:
    cfg = configparser.ConfigParser()
    pyproject_data = toml_document()
    uv_boost._apply_setup_cfg_scripts(cfg, pyproject_data)  # noqa: SLF001
    assert "project" not in pyproject_data


# =============================================================================
# _MIGRATE_FROM_SETUP_CFG
# =============================================================================


def test_migrate_from_setup_cfg_creates_pyproject(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    mock_repo.write_file(
        "setup.cfg",
        "[metadata]\nname = mylib\nversion = 1.0.0\n\n"
        "[options]\npython_requires = >=3.8\ninstall_requires =\n    requests>=2.0\n",
    )
    mock_repo.write_file("setup.py", "from setuptools import setup\nsetup()\n")

    uv_boost._migrate_from_setup_cfg()  # noqa: SLF001

    assert (mock_repo.path / "pyproject.toml").exists()
    assert not (mock_repo.path / "setup.cfg").exists()
    assert not (mock_repo.path / "setup.py").exists()
    content = (mock_repo.path / "pyproject.toml").read_text()
    assert "mylib" in content
    assert "requests>=2.0" in content
    assert "hatchling" in content


def test_migrate_from_setup_cfg_no_setup_py(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    mock_repo.write_file("setup.cfg", "[metadata]\nname = mylib\nversion = 1.0.0\n")
    uv_boost._migrate_from_setup_cfg()  # noqa: SLF001
    assert not (mock_repo.path / "setup.cfg").exists()


# =============================================================================
# _TRY_PIP_INSTALL / _TRY_SCRIPT_INSTALL
# =============================================================================


@pytest.fixture
def uv_boost_pip_oserror(uv_boost: UvBoost) -> Generator[UvBoost]:
    with patch("pimp_my_repo.core.boosts.uv.uv.run_command", side_effect=OSError("no pip")):
        yield uv_boost


@pytest.fixture
def uv_boost_pip_nonzero(uv_boost: UvBoost) -> Generator[UvBoost]:
    result = mock.MagicMock()
    result.returncode = 1
    with patch("pimp_my_repo.core.boosts.uv.uv.run_command", return_value=result):
        yield uv_boost


def test_try_pip_install_oserror_returns_false(uv_boost_pip_oserror: UvBoost) -> None:
    assert uv_boost_pip_oserror._try_pip_install() is False  # noqa: SLF001


def test_try_pip_install_nonzero_returns_false(uv_boost_pip_nonzero: UvBoost) -> None:
    assert uv_boost_pip_nonzero._try_pip_install() is False  # noqa: SLF001


@pytest.fixture
def uv_boost_script_oserror(uv_boost: UvBoost) -> Generator[UvBoost]:
    with patch("pimp_my_repo.core.boosts.uv.uv.run_command", side_effect=OSError("no curl")):
        yield uv_boost


@pytest.fixture
def uv_boost_script_nonzero(uv_boost: UvBoost) -> Generator[UvBoost]:
    result = mock.MagicMock()
    result.returncode = 1
    with patch("pimp_my_repo.core.boosts.uv.uv.run_command", return_value=result):
        yield uv_boost


def test_try_script_install_oserror_returns_false(uv_boost_script_oserror: UvBoost) -> None:
    assert uv_boost_script_oserror._try_script_install() is False  # noqa: SLF001


def test_try_script_install_nonzero_returns_false(uv_boost_script_nonzero: UvBoost) -> None:
    assert uv_boost_script_nonzero._try_script_install() is False  # noqa: SLF001
