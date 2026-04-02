"""Tests for PyProjectController."""

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from pimp_my_repo.core.tools.pyproject import PyProjectController

if TYPE_CHECKING:
    from pimp_my_repo.core.tools.repo import RepositoryController


@pytest.fixture
def pyproject(mock_repo: RepositoryController) -> PyProjectController:
    return PyProjectController(repo_path=mock_repo.path)


# =============================================================================
# is_package_in_deps
# =============================================================================


def test_is_package_in_deps_returns_false_on_oserror(pyproject: PyProjectController) -> None:
    with patch.object(pyproject, "read", side_effect=OSError):
        assert pyproject.is_package_in_deps("requests") is False


def test_is_package_in_deps_returns_false_on_value_error(pyproject: PyProjectController) -> None:
    with patch.object(pyproject, "read", side_effect=ValueError):
        assert pyproject.is_package_in_deps("requests") is False


def test_is_package_in_deps_found_in_dependency_groups(
    mock_repo: RepositoryController, pyproject: PyProjectController
) -> None:
    mock_repo.write_file(
        "pyproject.toml",
        '[dependency-groups]\ndev = ["pytest>=7.0", "requests>=2.0"]\n',
    )
    assert pyproject.is_package_in_deps("requests") is True


def test_is_package_in_deps_case_insensitive(mock_repo: RepositoryController, pyproject: PyProjectController) -> None:
    mock_repo.write_file("pyproject.toml", '[dependency-groups]\ndev = ["Requests>=2.0"]\n')
    assert pyproject.is_package_in_deps("requests") is True


def test_is_package_in_deps_found_in_optional_dependencies(
    mock_repo: RepositoryController, pyproject: PyProjectController
) -> None:
    mock_repo.write_file(
        "pyproject.toml",
        '[project.optional-dependencies]\nextra = ["requests>=2.0", "click>=8.0"]\n',
    )
    assert pyproject.is_package_in_deps("click") is True


def test_is_package_in_deps_not_found(mock_repo: RepositoryController, pyproject: PyProjectController) -> None:
    mock_repo.write_file("pyproject.toml", '[dependency-groups]\ndev = ["pytest>=7.0"]\n')
    assert pyproject.is_package_in_deps("requests") is False


# =============================================================================
# add_package_to_deps
# =============================================================================


def test_add_package_to_deps_creates_dependency_groups_section(
    mock_repo: RepositoryController, pyproject: PyProjectController
) -> None:
    mock_repo.write_file("pyproject.toml", '[project]\nname = "x"\n')
    pyproject.add_package_to_deps(group="dev", package="pytest>=7.0")
    content = (mock_repo.path / "pyproject.toml").read_text()
    assert "[dependency-groups]" in content
    assert "pytest>=7.0" in content


def test_add_package_to_deps_creates_new_group(mock_repo: RepositoryController, pyproject: PyProjectController) -> None:
    mock_repo.write_file("pyproject.toml", '[dependency-groups]\nlint = ["ruff"]\n')
    pyproject.add_package_to_deps(group="test", package="pytest>=7.0")
    content = (mock_repo.path / "pyproject.toml").read_text()
    assert "pytest>=7.0" in content
    assert "ruff" in content  # existing group preserved


def test_add_package_to_deps_appends_to_existing_group(
    mock_repo: RepositoryController, pyproject: PyProjectController
) -> None:
    mock_repo.write_file("pyproject.toml", '[dependency-groups]\ndev = ["pytest>=7.0"]\n')
    pyproject.add_package_to_deps(group="dev", package="requests>=2.0")
    content = (mock_repo.path / "pyproject.toml").read_text()
    assert "pytest>=7.0" in content
    assert "requests>=2.0" in content
