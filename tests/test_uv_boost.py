"""Tests for UV boost implementation."""

import re
import subprocess
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from pimp_my_repo.core.boosts.uv.detector import (
    detect_all,
    detect_dependency_files,
    detect_existing_configs,
)
from pimp_my_repo.core.boosts.uv.uv import UvBoost
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
        patch.object(uv_boost.tools.uv, "run"),
    ):
        yield uv_boost


@pytest.fixture
def uv_boost_with_migration_error(mock_repo: RepositoryController, uv_boost: UvBoost) -> Generator[UvBoost]:
    """Yield a UvBoost set up for poetry migration that will fail on run_uvx."""
    mock_repo.write_file("poetry.lock", "# Poetry lock file")
    mock_repo.write_file("pyproject.toml", "[tool.poetry]\nname = 'test'")
    error = subprocess.CalledProcessError(1, "uvx", stderr="Migration failed")
    with patch.object(uv_boost.tools.uv, "run_uvx", side_effect=error):
        yield uv_boost


@pytest.fixture
def uv_boost_with_lock_error(mock_repo: RepositoryController, uv_boost: UvBoost) -> Generator[UvBoost]:
    """Yield a UvBoost with a pyproject.toml that will fail on uv lock."""
    mock_repo.write_file("pyproject.toml", "[project]\nname = 'test'\nversion = '0.1.0'")
    error = subprocess.CalledProcessError(1, "uv lock", stderr="Lock failed")

    def run_side_effect(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:  # noqa: ARG001
        # Only raise error for "lock" command, not for "--version" check
        if args and args[0] == "lock":
            raise error
        # Return success for version check
        return subprocess.CompletedProcess(["uv", *args], 0, "", "")

    with patch.object(uv_boost.tools.uv, "run", side_effect=run_side_effect):
        yield uv_boost


@pytest.fixture
def uv_boost_check_called_process_error(uv_boost: UvBoost) -> Generator[UvBoost]:
    """Yield a UvBoost where uv.run raises CalledProcessError for version check."""
    error = subprocess.CalledProcessError(1, "uv --version")
    with patch.object(uv_boost.tools.uv, "run", side_effect=error):
        yield uv_boost


@pytest.fixture
def uv_boost_check_oserror(uv_boost: UvBoost) -> Generator[UvBoost]:
    """Yield a UvBoost where uv.run raises OSError for version check."""
    with patch.object(uv_boost.tools.uv, "run", side_effect=OSError("System error")):
        yield uv_boost


@pytest.fixture
def uv_boost_check_file_not_found(uv_boost: UvBoost) -> Generator[UvBoost]:
    """Yield a UvBoost where uv.run raises FileNotFoundError for version check."""
    with patch.object(uv_boost.tools.uv, "run", side_effect=FileNotFoundError("uv not found")):
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


# =============================================================================
# APPLY
# =============================================================================


def test_apply_with_poetry_migration(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    mock_repo.write_file("poetry.lock", "# Poetry lock file")
    pyproject_content = (
        '[tool.poetry]\nname = "test-project"\nversion = "0.1.0"\n\n'
        '[tool.poetry.dependencies]\npython = "^3.8"\nrequests = "^2.28.0"\n'
    )
    mock_repo.write_file("pyproject.toml", pyproject_content)

    uv_boost.apply()

    assert (mock_repo.path / "pyproject.toml").exists()
    assert (mock_repo.path / "uv.lock").exists()


def test_apply_with_requirements_txt(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    mock_repo.write_file("requirements.txt", "requests>=2.0.0\npytest>=7.0.0")

    uv_boost.apply()

    assert (mock_repo.path / "pyproject.toml").exists()
    assert (mock_repo.path / "uv.lock").exists()


def test_apply_creates_minimal_pyproject_when_no_source(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    uv_boost.apply()

    pyproject_path = mock_repo.path / "pyproject.toml"
    assert pyproject_path.exists()
    assert (mock_repo.path / "uv.lock").exists()

    pyproject_content = pyproject_path.read_text()
    assert "[project]" in pyproject_content
    assert "[tool.uv]" in pyproject_content


def test_apply_ensures_uv_config(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    pyproject_content = '[project]\nname = "test-project"\nversion = "0.1.0"\n'
    mock_repo.write_file("pyproject.toml", pyproject_content)

    uv_boost.apply()

    pyproject_content_after = (mock_repo.path / "pyproject.toml").read_text()
    assert "[tool.uv]" in pyproject_content_after


def test_apply_preserves_existing_pyproject(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    pyproject_content = (
        '[project]\nname = "test-project"\nversion = "0.1.0"\n'
        'description = "A test project"\n\n[tool.ruff]\nline-length = 120\n'
    )
    mock_repo.write_file("pyproject.toml", pyproject_content)

    uv_boost.apply()

    pyproject_content_after = (mock_repo.path / "pyproject.toml").read_text()
    assert 'description = "A test project"' in pyproject_content_after
    assert "[tool.ruff]" in pyproject_content_after
    assert "[tool.uv]" in pyproject_content_after


def test_apply_creates_uv_lock(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    uv_boost.apply()
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
    pyproject_data = uv_boost._ensure_uv_config(pyproject_data)  # noqa: SLF001
    uv_boost.tools.pyproject.write(pyproject_data)

    pyproject_content_after = (mock_repo.path / "pyproject.toml").read_text()
    assert "[tool.uv]" in pyproject_content_after


def test_ensure_uv_config_preserves_existing_section(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    pyproject_content = '[project]\nname = "test-project"\n\n[tool.uv]\npackage = true\ndev-dependencies = []\n'
    mock_repo.write_file("pyproject.toml", pyproject_content)

    pyproject_data = uv_boost.tools.pyproject.read()
    pyproject_data = uv_boost._ensure_uv_config(pyproject_data)  # noqa: SLF001
    uv_boost.tools.pyproject.write(pyproject_data)

    pyproject_content_after = (mock_repo.path / "pyproject.toml").read_text()
    assert "[tool.uv]" in pyproject_content_after
    assert "package = true" in pyproject_content_after


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
    pyproject_data = uv_boost._ensure_uv_config(pyproject_data)  # noqa: SLF001
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
    pyproject_data = uv_boost._ensure_uv_config(pyproject_data)  # noqa: SLF001
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


def test_has_migration_source_detects_setup_cfg(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    mock_repo.write_file("setup.cfg", "[metadata]\nname = myproject")
    assert uv_boost._has_migration_source() is True  # noqa: SLF001


def test_has_migration_source_ignores_bare_setup_py(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    """Bare setup.py without setup.cfg is not supported by migrate-to-uv."""
    mock_repo.write_file("setup.py", "from setuptools import setup\nsetup(name='myproject')")
    assert uv_boost._has_migration_source() is False  # noqa: SLF001


def test_has_migration_source_setup_cfg_with_setup_py(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    mock_repo.write_file("setup.py", "from setuptools import setup")
    mock_repo.write_file("setup.cfg", "[metadata]\nname = myproject")
    assert uv_boost._has_migration_source() is True  # noqa: SLF001


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


def test_apply_with_pipfile_migration(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    pipfile_content = '[packages]\nrequests = ">=2.0.0"\n\n[dev-packages]\npytest = ">=7.0.0"\n'
    mock_repo.write_file("Pipfile", pipfile_content)

    uv_boost.apply()

    assert (mock_repo.path / "pyproject.toml").exists()
    assert (mock_repo.path / "uv.lock").exists()


def test_apply_adds_grouped_requirements_files(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    """Test that grouped requirements files are added after migration."""
    mock_repo.write_file("requirements.txt", "requests>=2.0.0")
    mock_repo.write_file("requirements-dev.txt", "pytest>=7.0.0")
    mock_repo.write_file("test-requirements.txt", "pytest-cov>=4.0.0")

    with patch.object(uv_boost.tools.uv, "add_from_requirements_file") as mock_add:
        uv_boost.apply()

        # Should be called twice: once for dev, once for test
        expected_calls = 2
        assert mock_add.call_count == expected_calls

        # Check that dev group file was added
        dev_calls = [call for call in mock_add.call_args_list if call.kwargs.get("group") == "dev"]
        assert len(dev_calls) == 1
        assert dev_calls[0].args[0].name == "requirements-dev.txt"

        # Check that test group file was added
        test_calls = [call for call in mock_add.call_args_list if call.kwargs.get("group") == "test"]
        assert len(test_calls) == 1
        assert test_calls[0].args[0].name == "test-requirements.txt"


def test_apply_infers_project_name_from_directory(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    uv_boost.apply()

    content = (mock_repo.path / "pyproject.toml").read_text()
    assert "[project]" in content
    assert "name = " in content

    name_match = re.search(r'name = "([^"]+)"', content)
    assert name_match, "Could not find project name in pyproject.toml"
    project_name = name_match.group(1)
    assert project_name[0].isalnum(), f"Project name must start with alphanumeric, got: {project_name!r}"
    assert project_name[-1].isalnum(), f"Project name must end with alphanumeric, got: {project_name!r}"


# =============================================================================
# IDEMPOTENCY
# =============================================================================


def test_apply_is_idempotent(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    mock_repo.write_file("pyproject.toml", '[project]\nname = "test-project"\nversion = "0.1.0"\n')

    uv_boost.apply()
    first_content = (mock_repo.path / "pyproject.toml").read_text()

    uv_boost.apply()
    second_content = (mock_repo.path / "pyproject.toml").read_text()

    assert "[tool.uv]" in first_content
    assert "[tool.uv]" in second_content


def test_get_name_returns_correct_value() -> None:
    assert UvBoost.get_name() == "uv"
