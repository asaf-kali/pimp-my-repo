import sys
from typing import TYPE_CHECKING

import pytest

from pimp_my_repo.cli.main import main
from pimp_my_repo.core.tools.subprocess import run_command

if TYPE_CHECKING:
    from pimp_my_repo.core.tools.repo import RepositoryController

ALL_BOOST_NAMES = ["gitignore", "uv", "ruff", "mypy", "precommit", "justfile"]


def test_cli_is_working(mock_repo: RepositoryController) -> None:
    result = run_command(
        ["pimp-my-repo", "--path", str(mock_repo.path)],
        check=False,
    )
    assert result.returncode in (0, 1)
    assert "Pimping repository at:" in result.stdout


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
    assert "Pimping repository at:" in result.stdout


def test_list_flag_prints_boost_names() -> None:
    """--list prints all boost names and exits 0."""
    result = run_command(["pimp-my-repo", "--list"], check=False)
    assert result.returncode == 0
    for name in ALL_BOOST_NAMES:
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
