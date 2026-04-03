import sys
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from pimp_my_repo.cli.main import app, main
from pimp_my_repo.cli.runner import BoostRunResult
from pimp_my_repo.core.result import BoostResult, BoostResultStatus
from pimp_my_repo.core.tools.subprocess import run_command

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from pimp_my_repo.core.tools.repo import RepositoryController

_cli_runner = CliRunner()

ALL_BOOST_NAMES = ["gitignore", "uv", "ruff", "mypy", "precommit", "justfile"]
ALL_OPT_IN_NAMES = ["dmypy"]


def test_cli_is_working(mock_repo: RepositoryController) -> None:
    result = run_command(
        ["pimp-my-repo", "--path", str(mock_repo.path)],
        check=False,
    )
    assert result.returncode in (0, 1)
    assert "Boosting repository at:" in result.stdout


def test_main_is_working(mock_repo: RepositoryController) -> None:
    """Test that main function exits properly."""
    # Mock sys.argv to pass the path argument
    original_argv = sys.argv.copy()
    try:
        sys.argv = ["pimp-my-repo", "--path", str(mock_repo.path)]
        with pytest.raises(SystemExit) as exc_info:
            main()
        # Should exit with code 0 when git is clean, or code 1 when dirty
        assert exc_info.value.code in (0, 1)
    finally:
        sys.argv = original_argv


def test_cli_with_clean_git(mock_repo: RepositoryController) -> None:
    """Test CLI with a clean git repository."""
    result = run_command(
        ["pimp-my-repo", "--path", str(mock_repo.path)],
        check=False,
    )
    assert result.returncode in (0, 1)
    assert "Boosting repository at:" in result.stdout


def test_list_flag_prints_boost_names() -> None:
    """--list prints all boost names (default + opt-in) and exits 0."""
    result = run_command(["pimp-my-repo", "--list"], check=False)
    assert result.returncode == 0
    for name in ALL_BOOST_NAMES + ALL_OPT_IN_NAMES:
        assert name in result.stdout


def test_only_flag_filters_boosts(mock_repo: RepositoryController) -> None:
    """--only gitignore runs exactly 1 boost."""
    result = run_command(
        ["pimp-my-repo", "--path", str(mock_repo.path), "--only", "gitignore"],
        check=False,
    )
    assert result.returncode in (0, 1)
    assert "gitignore" in result.stdout
    # Other boost names should not appear as run results
    for name in ALL_BOOST_NAMES:
        if name != "gitignore":
            assert name not in result.stdout


def test_skip_flag_excludes_boost(mock_repo: RepositoryController) -> None:
    """--skip ruff runs 5 boosts (all except ruff)."""
    result = run_command(
        ["pimp-my-repo", "--path", str(mock_repo.path), "--skip", "ruff"],
        check=False,
    )
    assert result.returncode in (0, 1)
    assert "ruff" not in result.stdout
    assert "gitignore" in result.stdout


def test_only_and_skip_mutually_exclusive(mock_repo: RepositoryController) -> None:
    """--only and --skip together exit with an error."""
    result = run_command(
        ["pimp-my-repo", "--path", str(mock_repo.path), "--only", "ruff", "--skip", "mypy"],
        check=False,
    )
    assert result.returncode == 1
    assert "mutually exclusive" in result.stdout


def test_unknown_boost_name_errors(mock_repo: RepositoryController) -> None:
    """--only with an unknown boost name exits 1 with a helpful message."""
    result = run_command(
        ["pimp-my-repo", "--path", str(mock_repo.path), "--only", "nonexistent"],
        check=False,
    )
    assert result.returncode == 1
    assert "nonexistent" in result.stdout
    assert "Valid boosts" in result.stdout


# =============================================================================
# PATH VALIDATION (via CliRunner for coverage)
# =============================================================================


def test_validate_path_nonexistent_exits_1() -> None:
    result = _cli_runner.invoke(app, ["--path", "/nonexistent/path/that/does/not/exist"])
    assert result.exit_code == 1
    assert "Path does not exist" in result.output


def test_validate_path_not_a_directory(tmp_path: Path) -> None:
    file_path = tmp_path / "somefile.txt"
    file_path.write_text("hello")
    result = _cli_runner.invoke(app, ["--path", str(file_path)])
    assert result.exit_code == 1
    assert "Path is not a directory" in result.output


# =============================================================================
# SUMMARY PRINTING (via CliRunner with mocked run_boosts)
# =============================================================================


@pytest.fixture
def patched_run_boosts_no_applied(mock_repo: RepositoryController) -> Generator[RepositoryController]:
    run_result = BoostRunResult(
        results=[BoostResult(name="ruff", status=BoostResultStatus.SKIPPED, message="skipped")],
        log_path=None,
    )
    with patch("pimp_my_repo.cli.main.run_boosts", return_value=run_result):
        yield mock_repo


@pytest.fixture
def patched_run_boosts_with_failure(mock_repo: RepositoryController) -> Generator[RepositoryController]:
    run_result = BoostRunResult(
        results=[BoostResult(name="ruff", status=BoostResultStatus.FAILED, message="error")],
        log_path=None,
    )
    with patch("pimp_my_repo.cli.main.run_boosts", return_value=run_result):
        yield mock_repo


def test_print_summary_no_boosts_applied(
    patched_run_boosts_no_applied: RepositoryController,
) -> None:
    result = _cli_runner.invoke(app, ["--path", str(patched_run_boosts_no_applied.path)])
    assert "No boosts applied" in result.output


def test_print_summary_failed_boost_exits_1(
    patched_run_boosts_with_failure: RepositoryController,
) -> None:
    result = _cli_runner.invoke(app, ["--path", str(patched_run_boosts_with_failure.path)])
    assert result.exit_code == 1
    assert "failed" in result.output
