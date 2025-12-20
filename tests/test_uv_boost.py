"""Tests for UV boost implementation."""

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from pimp_my_repo.core.boost.uv.uv import UvBoost

if TYPE_CHECKING:
    from collections.abc import Generator

    from tests.utils.repo_controller import RepositoryController


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
