import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from pimp_my_repo.cli.main import main

if TYPE_CHECKING:
    from pimp_my_repo.core.tools.repo import RepositoryController


def test_cli_is_working(mock_repo: RepositoryController) -> None:
    result = subprocess.run(  # noqa: S603
        ["pimp-my-repo", "--path", str(mock_repo.path)],  # noqa: S607
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode in (0, 1)
    assert "Pimping repository at:" in result.stdout
    assert "Found" in result.stdout
    assert "boosts" in result.stdout


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
    # Run CLI on clean repo
    result = subprocess.run(  # noqa: S603
        ["pimp-my-repo", "--path", str(mock_repo.path)],  # noqa: S607
        check=False,
        capture_output=True,
        text=True,
    )
    # Should run successfully (exit code 0) or fail gracefully
    assert result.returncode in (0, 1)
    assert "Pimping repository at:" in result.stdout
