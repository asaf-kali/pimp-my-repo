"""Pytest configuration and shared fixtures."""

import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Protocol
from unittest.mock import MagicMock

import pytest

from pimp_my_repo.core.tools.boost_tools import BoostTools
from pimp_my_repo.core.tools.git import GitController
from tests.repo_controller import RepositoryController

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture
def mock_repo() -> Generator[RepositoryController]:
    """Create a temporary directory with an initialized git repository."""
    tmp_dir = TemporaryDirectory()
    tmp_path = Path(tmp_dir.name)

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)  # noqa: S607
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],  # noqa: S607
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],  # noqa: S607
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    repo = RepositoryController(tmp_path)
    repo.add_and_commit(relative_path="README.md", content="# Test", message="Initial commit")
    yield repo
    tmp_dir.cleanup()


class SubprocessResultFactory(Protocol):
    """Callable that builds a MagicMock simulating a subprocess result."""

    def __call__(self, output: str = "") -> MagicMock: ...


def _make_result(*, returncode: int, output: str) -> MagicMock:
    r = MagicMock()
    r.returncode = returncode
    r.stdout = output
    r.stderr = ""
    return r


@pytest.fixture
def ok_result() -> SubprocessResultFactory:
    """Build a MagicMock simulating a successful subprocess result."""

    def _factory(output: str = "") -> MagicMock:
        return _make_result(returncode=0, output=output)

    return _factory


@pytest.fixture
def fail_result() -> SubprocessResultFactory:
    """Build a MagicMock simulating a failed subprocess result."""

    def _factory(output: str = "") -> MagicMock:
        return _make_result(returncode=1, output=output)

    return _factory


@pytest.fixture
def git_controller(mock_repo: RepositoryController) -> GitController:
    return GitController(repo_path=mock_repo.path)


@pytest.fixture
def repo_controller(mock_repo: RepositoryController) -> RepositoryController:
    """Alias for mock_repo, used by boost fixtures that need a RepositoryController."""
    return mock_repo


@pytest.fixture
def boost_tools(mock_repo: RepositoryController) -> BoostTools:
    return BoostTools.create(repo_path=mock_repo.path)
