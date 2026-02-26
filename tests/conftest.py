"""Pytest configuration and shared fixtures."""

from typing import Protocol
from unittest.mock import MagicMock

import pytest

from tests.utils.repo_controller import RepositoryController, mock_repo

__all__ = ["RepositoryController", "mock_repo"]


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
