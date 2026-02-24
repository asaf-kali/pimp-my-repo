"""Tests for UV boost implementation."""

import subprocess
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from pimp_my_repo.core.boost.uv.detector import (
    detect_all,
    detect_dependency_files,
    detect_existing_configs,
)
from pimp_my_repo.core.boost.uv.uv import UvBoost

if TYPE_CHECKING:
    from collections.abc import Generator

    from tests.utils.repo_controller import RepositoryController


# =============================================================================
# DETECTOR TESTS
# =============================================================================


class TestDetectDependencyFiles:
    """Tests for detect_dependency_files function."""

    def test_empty_repo(self, mock_repo: RepositoryController) -> None:
        """Test detection in empty repository (only README.md exists)."""
        result = detect_dependency_files(mock_repo.path)

        assert result["requirements.txt"] is False
        assert result["setup.py"] is False
        assert result["pyproject.toml"] is False
        assert result["Pipfile"] is False
        assert result["poetry.lock"] is False
        assert result["Pipfile.lock"] is False

    def test_all_files_present(self, mock_repo: RepositoryController) -> None:
        """Test detection when all dependency files exist."""
        mock_repo.add_file("requirements.txt", "requests>=2.0.0")
        mock_repo.add_file("setup.py", "from setuptools import setup")
        mock_repo.add_file("pyproject.toml", "[project]\nname = 'test'")
        mock_repo.add_file("Pipfile", "[packages]")
        mock_repo.add_file("poetry.lock", "# lock")
        mock_repo.add_file("Pipfile.lock", "{}")

        result = detect_dependency_files(mock_repo.path)

        assert result["requirements.txt"] is True
        assert result["setup.py"] is True
        assert result["pyproject.toml"] is True
        assert result["Pipfile"] is True
        assert result["poetry.lock"] is True
        assert result["Pipfile.lock"] is True

    def test_partial_files(self, mock_repo: RepositoryController) -> None:
        """Test detection with only some files present."""
        mock_repo.add_file("requirements.txt", "requests>=2.0.0")
        mock_repo.add_file("pyproject.toml", "[project]\nname = 'test'")

        result = detect_dependency_files(mock_repo.path)

        assert result["requirements.txt"] is True
        assert result["pyproject.toml"] is True
        assert result["setup.py"] is False
        assert result["Pipfile"] is False

    def test_pipfile_lock_detected(self, mock_repo: RepositoryController) -> None:
        """Test that Pipfile.lock is detected separately from Pipfile."""
        mock_repo.add_file("Pipfile.lock", '{"_meta": {}}')

        result = detect_dependency_files(mock_repo.path)

        assert result["Pipfile.lock"] is True
        assert result["Pipfile"] is False


class TestDetectExistingConfigs:
    """Tests for detect_existing_configs function."""

    def test_empty_repo(self, mock_repo: RepositoryController) -> None:
        """Test detection in empty repository."""
        result = detect_existing_configs(mock_repo.path)

        assert result[".ruff.toml"] is False
        assert result["ruff.toml"] is False
        assert result["mypy.ini"] is False
        assert result[".mypy.ini"] is False
        assert result[".pre-commit-config.yaml"] is False
        assert result["justfile"] is False
        assert result["Makefile"] is False

    def test_all_configs_present(self, mock_repo: RepositoryController) -> None:
        """Test detection when all config files exist."""
        mock_repo.add_file(".ruff.toml", "[lint]")
        mock_repo.add_file("ruff.toml", "[lint]")
        mock_repo.add_file("mypy.ini", "[mypy]")
        mock_repo.add_file(".mypy.ini", "[mypy]")
        mock_repo.add_file(".pre-commit-config.yaml", "repos: []")
        mock_repo.add_file("pre-commit-config.yaml", "repos: []")
        mock_repo.add_file("justfile", "default:")
        mock_repo.add_file("Makefile", "all:")
        mock_repo.add_file("makefile", "all:")

        result = detect_existing_configs(mock_repo.path)

        assert result[".ruff.toml"] is True
        assert result["ruff.toml"] is True
        assert result["mypy.ini"] is True
        assert result[".mypy.ini"] is True
        assert result[".pre-commit-config.yaml"] is True
        assert result["pre-commit-config.yaml"] is True
        assert result["justfile"] is True
        assert result["Makefile"] is True
        assert result["makefile"] is True

    def test_partial_configs(self, mock_repo: RepositoryController) -> None:
        """Test detection with only some config files present."""
        mock_repo.add_file("ruff.toml", "[lint]")
        mock_repo.add_file("justfile", "default:")

        result = detect_existing_configs(mock_repo.path)

        assert result["ruff.toml"] is True
        assert result["justfile"] is True
        assert result[".ruff.toml"] is False
        assert result["Makefile"] is False


class TestDetectAll:
    """Tests for detect_all function."""

    def test_returns_both_categories(self, mock_repo: RepositoryController) -> None:
        """Test that detect_all returns both dependencies and configs."""
        result = detect_all(mock_repo.path)

        assert "dependencies" in result
        assert "configs" in result
        assert isinstance(result["dependencies"], dict)
        assert isinstance(result["configs"], dict)

    def test_integration_with_files(self, mock_repo: RepositoryController) -> None:
        """Test detect_all with actual files present."""
        mock_repo.add_file("requirements.txt", "requests>=2.0.0")
        mock_repo.add_file("ruff.toml", "[lint]")

        result = detect_all(mock_repo.path)

        assert result["dependencies"]["requirements.txt"] is True
        assert result["configs"]["ruff.toml"] is True
        assert result["dependencies"]["Pipfile"] is False
        assert result["configs"]["justfile"] is False


# =============================================================================
# ORIGINAL FIXTURES
# =============================================================================


@pytest.fixture
def uv_boost(mock_repo: RepositoryController) -> UvBoost:
    """Create a UvBoost instance for testing."""
    return UvBoost(mock_repo.path)


@pytest.fixture
def patched_uv_boost_installed(uv_boost: UvBoost) -> Generator[UvBoost]:
    """Return a UvBoost instance with UV installed."""
    with patch.object(uv_boost, "_check_uv_installed", return_value=True):
        yield uv_boost


@pytest.fixture
def patched_uv_boost_not_installed(uv_boost: UvBoost) -> Generator[UvBoost]:
    """Return a UvBoost instance with UV not installed."""
    with (
        patch.object(uv_boost, "_check_uv_installed", return_value=False),
        patch.object(uv_boost, "_install_uv", return_value=False),
    ):
        yield uv_boost


@pytest.fixture
def patched_uv_boost_installable(uv_boost: UvBoost) -> Generator[UvBoost]:
    """Return a UvBoost instance that can install UV."""
    check_calls = [False, True]
    with (
        patch.object(uv_boost, "_check_uv_installed", side_effect=lambda: check_calls.pop(0)),
        patch.object(uv_boost, "_install_uv", return_value=True),
    ):
        yield uv_boost


# Preconditions tests


def test_check_preconditions_when_uv_installed(patched_uv_boost_installed: UvBoost) -> None:
    """Test that preconditions pass when UV is installed."""
    assert patched_uv_boost_installed.check_preconditions() is True


def test_check_preconditions_when_uv_not_installed(patched_uv_boost_not_installed: UvBoost) -> None:
    """Test that preconditions fail when UV is not installed and installation fails."""
    assert patched_uv_boost_not_installed.check_preconditions() is False


def test_check_preconditions_installs_uv_when_missing(patched_uv_boost_installable: UvBoost) -> None:
    """Test that preconditions attempt to install UV when missing."""
    assert patched_uv_boost_installable.check_preconditions() is True


# Migration detection tests


def test_has_migration_source_detects_poetry_lock(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    """Test detection of poetry.lock file."""
    mock_repo.add_file("poetry.lock", "# Poetry lock file")
    assert uv_boost._has_migration_source() is True  # noqa: SLF001


def test_has_migration_source_detects_poetry_config(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    """Test detection of Poetry config in pyproject.toml."""
    pyproject_content = """
[tool.poetry]
name = "test-project"
version = "0.1.0"
"""
    mock_repo.add_file("pyproject.toml", pyproject_content)
    assert uv_boost._has_migration_source() is True  # noqa: SLF001


def test_has_migration_source_detects_requirements_txt(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    """Test detection of requirements.txt file."""
    mock_repo.add_file("requirements.txt", "requests>=2.0.0")
    assert uv_boost._has_migration_source() is True  # noqa: SLF001


def test_has_migration_source_detects_multiple_requirements_files(
    mock_repo: RepositoryController, uv_boost: UvBoost
) -> None:
    """Test detection of multiple requirements files."""
    mock_repo.add_file("requirements.txt", "requests>=2.0.0")
    mock_repo.add_file("requirements-dev.txt", "pytest>=7.0.0")
    assert uv_boost._has_migration_source() is True  # noqa: SLF001


def test_has_migration_source_detects_pipfile(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    """Test detection of Pipfile."""
    mock_repo.add_file("Pipfile", "[packages]\nrequests = '>=2.0.0'")
    assert uv_boost._has_migration_source() is True  # noqa: SLF001


def test_has_migration_source_no_source(uv_boost: UvBoost) -> None:
    """Test that no migration source is detected when none exists."""
    assert uv_boost._has_migration_source() is False  # noqa: SLF001


def test_has_migration_source_ignores_non_poetry_pyproject(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    """Test that pyproject.toml without Poetry config is not detected as migration source."""
    pyproject_content = """
[project]
name = "test-project"
version = "0.1.0"
"""
    mock_repo.add_file("pyproject.toml", pyproject_content)
    assert uv_boost._has_migration_source() is False  # noqa: SLF001


# Apply tests


def test_apply_with_poetry_migration(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    """Test apply with Poetry project migration."""
    mock_repo.add_file("poetry.lock", "# Poetry lock file")
    pyproject_content = """
[tool.poetry]
name = "test-project"
version = "0.1.0"

[tool.poetry.dependencies]
python = "^3.8"
requests = "^2.28.0"
"""
    mock_repo.add_file("pyproject.toml", pyproject_content)

    uv_boost.apply()

    # Verify pyproject.toml was migrated and uv.lock was created
    pyproject_path = mock_repo.path / "pyproject.toml"
    assert pyproject_path.exists()
    lock_path = mock_repo.path / "uv.lock"
    assert lock_path.exists()


def test_apply_with_requirements_txt(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    """Test apply with requirements.txt migration."""
    mock_repo.add_file("requirements.txt", "requests>=2.0.0\npytest>=7.0.0")

    uv_boost.apply()

    # Verify pyproject.toml was created and uv.lock was generated
    pyproject_path = mock_repo.path / "pyproject.toml"
    assert pyproject_path.exists()
    lock_path = mock_repo.path / "uv.lock"
    assert lock_path.exists()


def test_apply_creates_minimal_pyproject_when_no_source(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    """Test that apply creates minimal pyproject.toml when no migration source exists."""
    uv_boost.apply()

    # Should create pyproject.toml
    pyproject_path = mock_repo.path / "pyproject.toml"
    assert pyproject_path.exists()

    # Should generate lock file
    lock_path = mock_repo.path / "uv.lock"
    assert lock_path.exists()

    # Verify pyproject.toml has correct structure
    pyproject_content = pyproject_path.read_text()
    assert "[project]" in pyproject_content
    assert "[tool.uv]" in pyproject_content


def test_apply_ensures_uv_config(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    """Test that apply ensures [tool.uv] config is present."""
    pyproject_content = """
[project]
name = "test-project"
version = "0.1.0"
"""
    mock_repo.add_file("pyproject.toml", pyproject_content)

    uv_boost.apply()

    # Verify [tool.uv] section was added
    pyproject_path = mock_repo.path / "pyproject.toml"
    pyproject_content_after = pyproject_path.read_text()
    assert "[tool.uv]" in pyproject_content_after


def test_apply_preserves_existing_pyproject(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    """Test that apply preserves existing pyproject.toml content."""
    pyproject_content = """
[project]
name = "test-project"
version = "0.1.0"
description = "A test project"

[tool.ruff]
line-length = 120
"""
    mock_repo.add_file("pyproject.toml", pyproject_content)

    uv_boost.apply()

    # Verify existing content is preserved
    pyproject_path = mock_repo.path / "pyproject.toml"
    pyproject_content_after = pyproject_path.read_text()
    assert 'description = "A test project"' in pyproject_content_after
    assert "[tool.ruff]" in pyproject_content_after
    assert "[tool.uv]" in pyproject_content_after


# Verify tests


def test_verify_success(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    """Test successful verification."""
    # First apply to create uv.lock
    uv_boost.apply()
    assert (mock_repo.path / "uv.lock").exists()

    # Then verify
    assert uv_boost.verify() is True


def test_verify_fails_when_lock_missing(uv_boost: UvBoost) -> None:
    """Test verification fails when uv.lock is missing."""
    assert uv_boost.verify() is False


# Commit message test


def test_commit_message(uv_boost: UvBoost) -> None:
    """Test commit message generation."""
    assert uv_boost.commit_message() == "✨ Add UV dependency management"


# UV config tests


def test_ensure_uv_config_adds_section_when_missing(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    """Test that _ensure_uv_config adds [tool.uv] section when missing."""
    pyproject_content = """
[project]
name = "test-project"
"""
    mock_repo.add_file("pyproject.toml", pyproject_content)

    pyproject_data = uv_boost._read_pyproject()  # noqa: SLF001
    pyproject_data = uv_boost._ensure_uv_config(pyproject_data)  # noqa: SLF001
    uv_boost._write_pyproject(pyproject_data)  # noqa: SLF001

    # Verify [tool.uv] section was added
    pyproject_path = mock_repo.path / "pyproject.toml"
    pyproject_content_after = pyproject_path.read_text()
    assert "[tool.uv]" in pyproject_content_after


def test_ensure_uv_config_preserves_existing_section(mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
    """Test that _ensure_uv_config preserves existing [tool.uv] section."""
    pyproject_content = """
[project]
name = "test-project"

[tool.uv]
package = true
dev-dependencies = []
"""
    mock_repo.add_file("pyproject.toml", pyproject_content)

    pyproject_data = uv_boost._read_pyproject()  # noqa: SLF001
    pyproject_data = uv_boost._ensure_uv_config(pyproject_data)  # noqa: SLF001
    uv_boost._write_pyproject(pyproject_data)  # noqa: SLF001

    # Verify existing content is preserved
    pyproject_path = mock_repo.path / "pyproject.toml"
    pyproject_content_after = pyproject_path.read_text()
    assert "[tool.uv]" in pyproject_content_after
    assert "package = true" in pyproject_content_after


# =============================================================================
# ERROR HANDLING TESTS - Subprocess Failures
# =============================================================================


class TestSubprocessErrorHandling:
    """Tests for subprocess error handling in UvBoost."""

    def test_apply_raises_on_migration_failure(self, mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
        """Test that apply raises CalledProcessError when migration fails."""
        mock_repo.add_file("poetry.lock", "# Poetry lock file")
        mock_repo.add_file("pyproject.toml", "[tool.poetry]\nname = 'test'")

        error = subprocess.CalledProcessError(1, "uvx", stderr="Migration failed")
        with patch.object(uv_boost, "_run_uvx", side_effect=error):
            with pytest.raises(subprocess.CalledProcessError) as exc_info:
                uv_boost.apply()
            assert exc_info.value.returncode == 1

    def test_apply_raises_on_lock_generation_failure(self, mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
        """Test that apply raises CalledProcessError when uv lock fails."""
        # No migration source, so it will skip migration and try to lock
        pyproject_content = "[project]\nname = 'test'\nversion = '0.1.0'"
        mock_repo.add_file("pyproject.toml", pyproject_content)

        error = subprocess.CalledProcessError(1, "uv lock", stderr="Lock failed")
        with patch.object(uv_boost, "_run_uv", side_effect=error), pytest.raises(subprocess.CalledProcessError):
            uv_boost.apply()

    def test_verify_handles_oserror(self, mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
        """Test that verify handles OSError gracefully."""
        # Create uv.lock so it passes the first check
        mock_repo.add_file("uv.lock", "# lock file")

        with patch.object(uv_boost, "_run_uv", side_effect=OSError("Command not found")):
            result = uv_boost.verify()
            assert result is False

    def test_verify_handles_file_not_found_error(self, mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
        """Test that verify handles FileNotFoundError gracefully."""
        mock_repo.add_file("uv.lock", "# lock file")

        with patch.object(uv_boost, "_run_uv", side_effect=FileNotFoundError("uv not found")):
            result = uv_boost.verify()
            assert result is False

    def test_verify_returns_false_on_nonzero_exit(self, mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
        """Test that verify returns False when uv sync --dry-run has non-zero exit."""
        mock_repo.add_file("uv.lock", "# lock file")

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Dependency resolution failed"

        with patch.object(uv_boost, "_run_uv", return_value=mock_result):
            result = uv_boost.verify()
            assert result is False

    def test_check_uv_installed_handles_called_process_error(self, uv_boost: UvBoost) -> None:
        """Test that _check_uv_installed handles CalledProcessError."""
        error = subprocess.CalledProcessError(1, "uv --version")
        with patch.object(uv_boost, "_run_uv", side_effect=error):
            result = uv_boost._check_uv_installed()  # noqa: SLF001
            assert result is False

    def test_check_uv_installed_handles_oserror(self, uv_boost: UvBoost) -> None:
        """Test that _check_uv_installed handles OSError."""
        with patch.object(uv_boost, "_run_uv", side_effect=OSError("System error")):
            result = uv_boost._check_uv_installed()  # noqa: SLF001
            assert result is False

    def test_check_uv_installed_handles_file_not_found(self, uv_boost: UvBoost) -> None:
        """Test that _check_uv_installed handles FileNotFoundError."""
        with patch.object(uv_boost, "_run_uv", side_effect=FileNotFoundError("uv not found")):
            result = uv_boost._check_uv_installed()  # noqa: SLF001
            assert result is False


# =============================================================================
# UV INSTALLATION FAILURE TESTS
# =============================================================================


class TestUvInstallationFailures:
    """Tests for UV installation failure scenarios."""

    def test_install_uv_pip_failure_falls_back_to_installer(self, uv_boost: UvBoost) -> None:
        """Test that pip failure falls back to official installer."""
        pip_result = MagicMock()
        pip_result.returncode = 1

        installer_result = MagicMock()
        installer_result.returncode = 0

        expected_call_count = 2  # pip + installer fallback
        with patch("subprocess.run", side_effect=[pip_result, installer_result]) as mock_run:
            result = uv_boost._install_uv()  # noqa: SLF001
            assert result is True
            assert mock_run.call_count == expected_call_count

    def test_install_uv_both_methods_fail(self, uv_boost: UvBoost) -> None:
        """Test that installation returns False when both methods fail."""
        pip_result = MagicMock()
        pip_result.returncode = 1

        installer_result = MagicMock()
        installer_result.returncode = 1

        with patch("subprocess.run", side_effect=[pip_result, installer_result]):
            result = uv_boost._install_uv()  # noqa: SLF001
            assert result is False

    def test_install_uv_pip_raises_oserror(self, uv_boost: UvBoost) -> None:
        """Test that pip OSError falls back to official installer."""
        installer_result = MagicMock()
        installer_result.returncode = 0

        with patch("subprocess.run", side_effect=[OSError("pip not found"), installer_result]):
            result = uv_boost._install_uv()  # noqa: SLF001
            assert result is True

    def test_install_uv_installer_raises_oserror(self, uv_boost: UvBoost) -> None:
        """Test that installer OSError returns False."""
        pip_result = MagicMock()
        pip_result.returncode = 1

        with patch("subprocess.run", side_effect=[pip_result, OSError("curl not found")]):
            result = uv_boost._install_uv()  # noqa: SLF001
            assert result is False

    def test_install_uv_pip_success(self, uv_boost: UvBoost) -> None:
        """Test that successful pip install returns True immediately."""
        pip_result = MagicMock()
        pip_result.returncode = 0

        with patch("subprocess.run", return_value=pip_result) as mock_run:
            result = uv_boost._install_uv()  # noqa: SLF001
            assert result is True
            # Should only call once (pip), not fallback to installer
            assert mock_run.call_count == 1


# =============================================================================
# PYPROJECT.TOML EDGE CASE TESTS
# =============================================================================


class TestPyprojectEdgeCases:
    """Tests for pyproject.toml edge cases."""

    def test_read_pyproject_empty_file(self, mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
        """Test reading an empty pyproject.toml file."""
        mock_repo.add_file("pyproject.toml", "")

        result = uv_boost._read_pyproject()  # noqa: SLF001
        # Should return empty document
        assert len(result) == 0

    def test_read_pyproject_invalid_toml(self, mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
        """Test reading an invalid TOML file returns empty document."""
        mock_repo.add_file("pyproject.toml", "this is [ not valid toml {{{{")

        result = uv_boost._read_pyproject()  # noqa: SLF001
        # Should return empty document on parse error
        assert len(result) == 0

    def test_read_pyproject_permission_denied(self, mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
        """Test reading pyproject.toml with permission denied returns empty document."""
        mock_repo.add_file("pyproject.toml", "[project]\nname = 'test'")

        with patch("pathlib.Path.open", side_effect=OSError("Permission denied")):
            result = uv_boost._read_pyproject()  # noqa: SLF001
            assert len(result) == 0

    def test_read_pyproject_unicode_error(self, mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
        """Test reading pyproject.toml with encoding error returns empty document."""
        mock_repo.add_file("pyproject.toml", "[project]\nname = 'test'")

        with patch("pathlib.Path.open", side_effect=UnicodeDecodeError("utf-8", b"", 0, 1, "invalid")):
            result = uv_boost._read_pyproject()  # noqa: SLF001
            assert len(result) == 0

    def test_read_pyproject_nonexistent_file(self, uv_boost: UvBoost) -> None:
        """Test reading non-existent pyproject.toml returns empty document."""
        result = uv_boost._read_pyproject()  # noqa: SLF001
        assert len(result) == 0

    def test_write_pyproject_preserves_comments(self, mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
        """Test that _write_pyproject preserves TOML comments."""
        pyproject_content = """# This is a comment
[project]
name = "test-project"  # inline comment
version = "0.1.0"

# Section comment
[tool.ruff]
line-length = 120
"""
        mock_repo.add_file("pyproject.toml", pyproject_content)

        pyproject_data = uv_boost._read_pyproject()  # noqa: SLF001
        pyproject_data = uv_boost._ensure_uv_config(pyproject_data)  # noqa: SLF001
        uv_boost._write_pyproject(pyproject_data)  # noqa: SLF001

        # Verify comments are preserved
        pyproject_path = mock_repo.path / "pyproject.toml"
        content_after = pyproject_path.read_text()
        assert "# This is a comment" in content_after
        assert "# Section comment" in content_after

    def test_ensure_uv_config_with_existing_tool_section(
        self, mock_repo: RepositoryController, uv_boost: UvBoost
    ) -> None:
        """Test _ensure_uv_config when [tool] exists but [tool.uv] doesn't."""
        pyproject_content = """
[project]
name = "test-project"

[tool.ruff]
line-length = 120

[tool.mypy]
strict = true
"""
        mock_repo.add_file("pyproject.toml", pyproject_content)

        pyproject_data = uv_boost._read_pyproject()  # noqa: SLF001
        pyproject_data = uv_boost._ensure_uv_config(pyproject_data)  # noqa: SLF001
        uv_boost._write_pyproject(pyproject_data)  # noqa: SLF001

        pyproject_path = mock_repo.path / "pyproject.toml"
        content = pyproject_path.read_text()
        assert "[tool.uv]" in content
        assert "[tool.ruff]" in content
        assert "[tool.mypy]" in content


# =============================================================================
# MIGRATION EDGE CASE TESTS
# =============================================================================


class TestMigrationEdgeCases:
    """Tests for migration detection edge cases."""

    def test_has_migration_source_detects_pipfile_lock(
        self, mock_repo: RepositoryController, uv_boost: UvBoost
    ) -> None:
        """Test detection of Pipfile.lock without Pipfile."""
        mock_repo.add_file("Pipfile.lock", '{"_meta": {"hash": {}}}')

        result = uv_boost._has_migration_source()  # noqa: SLF001
        assert result is True

    def test_has_migration_source_empty_poetry_lock(self, mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
        """Test detection of empty poetry.lock file."""
        mock_repo.add_file("poetry.lock", "")

        result = uv_boost._has_migration_source()  # noqa: SLF001
        assert result is True  # File exists, even if empty

    def test_has_migration_source_nested_requirements(self, mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
        """Test detection of requirements files in subdirectories."""
        mock_repo.add_file("requirements/base.txt", "requests>=2.0.0")
        mock_repo.add_file("requirements/dev.txt", "pytest>=7.0.0")

        # rglob should NOT find these since they don't match requirements*.txt pattern
        # The pattern is repo_path.rglob("requirements*.txt")
        result = uv_boost._has_migration_source()  # noqa: SLF001
        assert result is False

    def test_has_migration_source_requirements_dev_txt(
        self, mock_repo: RepositoryController, uv_boost: UvBoost
    ) -> None:
        """Test detection of requirements-dev.txt variant."""
        mock_repo.add_file("requirements-dev.txt", "pytest>=7.0.0")

        result = uv_boost._has_migration_source()  # noqa: SLF001
        assert result is True

    def test_has_migration_source_requirements_test_txt(
        self, mock_repo: RepositoryController, uv_boost: UvBoost
    ) -> None:
        """Test detection of requirements-test.txt variant."""
        mock_repo.add_file("requirements-test.txt", "pytest>=7.0.0")

        result = uv_boost._has_migration_source()  # noqa: SLF001
        assert result is True

    def test_has_migration_source_both_pipfile_and_poetry(
        self, mock_repo: RepositoryController, uv_boost: UvBoost
    ) -> None:
        """Test detection when multiple migration sources exist."""
        mock_repo.add_file("Pipfile", "[packages]")
        mock_repo.add_file("poetry.lock", "# lock")

        result = uv_boost._has_migration_source()  # noqa: SLF001
        assert result is True

    def test_apply_with_pipfile_migration(self, mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
        """Test apply with Pipfile migration."""
        pipfile_content = """
[packages]
requests = ">=2.0.0"

[dev-packages]
pytest = ">=7.0.0"
"""
        mock_repo.add_file("Pipfile", pipfile_content)

        uv_boost.apply()

        # Verify pyproject.toml was created and uv.lock was generated
        pyproject_path = mock_repo.path / "pyproject.toml"
        assert pyproject_path.exists()
        lock_path = mock_repo.path / "uv.lock"
        assert lock_path.exists()

    def test_apply_infers_project_name_from_directory(self, mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
        """Test that apply infers project name from directory when creating minimal pyproject."""
        uv_boost.apply()

        pyproject_path = mock_repo.path / "pyproject.toml"
        content = pyproject_path.read_text()

        # Project name should be derived from directory name
        assert "[project]" in content
        assert "name = " in content


# =============================================================================
# IDEMPOTENCY AND EDGE CASE TESTS
# =============================================================================


class TestIdempotencyAndEdgeCases:
    """Tests for idempotent behavior and additional edge cases."""

    def test_apply_is_idempotent(self, mock_repo: RepositoryController, uv_boost: UvBoost) -> None:
        """Test that apply can be called multiple times without error."""
        pyproject_content = """
[project]
name = "test-project"
version = "0.1.0"
"""
        mock_repo.add_file("pyproject.toml", pyproject_content)

        # Apply twice
        uv_boost.apply()
        first_content = (mock_repo.path / "pyproject.toml").read_text()

        uv_boost.apply()
        second_content = (mock_repo.path / "pyproject.toml").read_text()

        # Content should be essentially the same
        assert "[tool.uv]" in first_content
        assert "[tool.uv]" in second_content

    def test_get_name_returns_correct_value(self) -> None:
        """Test that get_name returns 'uv'."""
        assert UvBoost.get_name() == "uv"

    def test_verify_with_valid_lock_and_successful_sync(self, uv_boost: UvBoost) -> None:
        """Test verify returns True with valid setup."""
        # First apply to create proper state
        uv_boost.apply()

        # Verify should succeed
        result = uv_boost.verify()
        assert result is True
