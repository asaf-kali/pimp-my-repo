"""Tests for python version resolution in UV boost."""

from typing import TYPE_CHECKING
from unittest import mock

import pytest

from pimp_my_repo.core.boosts.uv.python_version import PythonVersion, resolve_requires_python

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_detect_venv() -> Generator[mock.MagicMock]:
    with mock.patch("pimp_my_repo.core.boosts.uv.python_version._detect_venv_python_version") as m:
        yield m


@pytest.fixture
def mock_detect_uv_lock() -> Generator[mock.MagicMock]:
    with mock.patch("pimp_my_repo.core.boosts.uv.python_version._detect_from_uv_lock") as m:
        yield m


@pytest.fixture
def mock_detect_vermin() -> Generator[mock.MagicMock]:
    with mock.patch("pimp_my_repo.core.boosts.uv.python_version._detect_vermin_min_version") as m:
        yield m


@pytest.fixture
def mock_run_command() -> Generator[mock.MagicMock]:
    with mock.patch("pimp_my_repo.core.boosts.uv.python_version.run_command") as m:
        yield m


# =============================================================================
# resolve_requires_python TESTS
# =============================================================================


def test_resolve_prefers_venv_over_uv_lock(
    mock_detect_venv: mock.MagicMock,
    mock_detect_uv_lock: mock.MagicMock,
    mock_detect_vermin: mock.MagicMock,
    tmp_path: Path,
) -> None:
    mock_detect_venv.return_value = PythonVersion(major=3, minor=11)
    mock_detect_uv_lock.return_value = PythonVersion(major=3, minor=14)
    mock_detect_vermin.return_value = PythonVersion(major=3, minor=8)

    result = resolve_requires_python(repo_path=tmp_path)

    assert result == ">=3.11"
    mock_detect_uv_lock.assert_not_called()
    mock_detect_vermin.assert_not_called()


def test_resolve_prefers_uv_lock_over_vermin(
    mock_detect_venv: mock.MagicMock,
    mock_detect_uv_lock: mock.MagicMock,
    mock_detect_vermin: mock.MagicMock,
    tmp_path: Path,
) -> None:
    mock_detect_venv.return_value = None
    mock_detect_uv_lock.return_value = PythonVersion(major=3, minor=14)
    mock_detect_vermin.return_value = PythonVersion(major=3, minor=8)

    result = resolve_requires_python(repo_path=tmp_path)

    assert result == ">=3.14"
    mock_detect_vermin.assert_not_called()


def test_resolve_falls_back_to_vermin(
    mock_detect_venv: mock.MagicMock,
    mock_detect_uv_lock: mock.MagicMock,
    mock_detect_vermin: mock.MagicMock,
    tmp_path: Path,
) -> None:
    mock_detect_venv.return_value = None
    mock_detect_uv_lock.return_value = None
    mock_detect_vermin.return_value = PythonVersion(major=3, minor=10)

    result = resolve_requires_python(repo_path=tmp_path)

    assert result == ">=3.10"


def test_resolve_returns_none_when_all_fail(
    mock_detect_venv: mock.MagicMock,
    mock_detect_uv_lock: mock.MagicMock,
    mock_detect_vermin: mock.MagicMock,
    tmp_path: Path,
) -> None:
    mock_detect_venv.return_value = None
    mock_detect_uv_lock.return_value = None
    mock_detect_vermin.return_value = None

    result = resolve_requires_python(repo_path=tmp_path)

    assert result is None


# =============================================================================
# _detect_venv_python_version TESTS
# =============================================================================


def test_detect_venv_finds_dotenv_dir(
    mock_run_command: mock.MagicMock,
    mock_detect_uv_lock: mock.MagicMock,
    mock_detect_vermin: mock.MagicMock,
    tmp_path: Path,
) -> None:
    mock_detect_uv_lock.return_value = None
    mock_detect_vermin.return_value = None
    venv_dir = tmp_path / ".venv" / "bin"
    venv_dir.mkdir(parents=True)
    python_exe = venv_dir / "python"
    python_exe.write_text("#!/bin/sh\necho 'Python 3.11.5'")
    python_exe.chmod(0o755)

    result_mock = mock.MagicMock()
    result_mock.stdout = "Python 3.11.5"
    result_mock.stderr = ""
    mock_run_command.return_value = result_mock

    result = resolve_requires_python(repo_path=tmp_path)

    assert result == ">=3.11"
    mock_run_command.assert_called_once_with(
        [str(python_exe), "--version"],
        cwd=tmp_path,
        check=False,
    )


# =============================================================================
# _detect_from_uv_lock TESTS
# =============================================================================


def test_detect_from_uv_lock_parses_version(
    mock_detect_venv: mock.MagicMock,
    mock_detect_vermin: mock.MagicMock,
    tmp_path: Path,
) -> None:
    mock_detect_venv.return_value = None
    mock_detect_vermin.return_value = None
    (tmp_path / "uv.lock").write_text('version = 1\nrequires-python = ">=3.14"\n')

    result = resolve_requires_python(repo_path=tmp_path)

    assert result == ">=3.14"


def test_detect_from_uv_lock_no_file(
    mock_detect_venv: mock.MagicMock,
    mock_detect_vermin: mock.MagicMock,
    tmp_path: Path,
) -> None:
    mock_detect_venv.return_value = None
    mock_detect_vermin.return_value = None

    result = resolve_requires_python(repo_path=tmp_path)

    assert result is None


# =============================================================================
# _detect_vermin_min_version TESTS
# =============================================================================


def test_detect_vermin_parses_output(
    mock_run_command: mock.MagicMock,
    mock_detect_venv: mock.MagicMock,
    mock_detect_uv_lock: mock.MagicMock,
    tmp_path: Path,
) -> None:
    mock_detect_venv.return_value = None
    mock_detect_uv_lock.return_value = None
    result_mock = mock.MagicMock()
    result_mock.stdout = "Minimum required versions: 3.9"
    result_mock.stderr = ""
    mock_run_command.return_value = result_mock

    result = resolve_requires_python(repo_path=tmp_path)

    assert result == ">=3.9"


def test_detect_vermin_handles_py2_and_py3_output(
    mock_run_command: mock.MagicMock,
    mock_detect_venv: mock.MagicMock,
    mock_detect_uv_lock: mock.MagicMock,
    tmp_path: Path,
) -> None:
    mock_detect_venv.return_value = None
    mock_detect_uv_lock.return_value = None
    result_mock = mock.MagicMock()
    result_mock.stdout = "Minimum required versions: 2.7, 3.6"
    result_mock.stderr = ""
    mock_run_command.return_value = result_mock

    result = resolve_requires_python(repo_path=tmp_path)

    assert result == ">=3.6"


def test_detect_vermin_returns_none_on_oserror(
    mock_run_command: mock.MagicMock,
    mock_detect_venv: mock.MagicMock,
    mock_detect_uv_lock: mock.MagicMock,
    tmp_path: Path,
) -> None:
    mock_detect_venv.return_value = None
    mock_detect_uv_lock.return_value = None
    mock_run_command.side_effect = OSError("vermin not found")

    result = resolve_requires_python(repo_path=tmp_path)

    assert result is None


def test_detect_vermin_returns_none_when_no_py3(
    mock_run_command: mock.MagicMock,
    mock_detect_venv: mock.MagicMock,
    mock_detect_uv_lock: mock.MagicMock,
    tmp_path: Path,
) -> None:
    mock_detect_venv.return_value = None
    mock_detect_uv_lock.return_value = None
    result_mock = mock.MagicMock()
    result_mock.stdout = "Minimum required versions: 2.7"
    result_mock.stderr = ""
    mock_run_command.return_value = result_mock

    result = resolve_requires_python(repo_path=tmp_path)

    assert result is None


def test_detect_vermin_returns_none_when_output_empty(
    mock_run_command: mock.MagicMock,
    mock_detect_venv: mock.MagicMock,
    mock_detect_uv_lock: mock.MagicMock,
    tmp_path: Path,
) -> None:
    mock_detect_venv.return_value = None
    mock_detect_uv_lock.return_value = None
    result_mock = mock.MagicMock()
    result_mock.stdout = ""
    result_mock.stderr = ""
    mock_run_command.return_value = result_mock

    result = resolve_requires_python(repo_path=tmp_path)

    assert result is None
