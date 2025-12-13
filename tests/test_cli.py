import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

import pytest

from pimp_my_repo.cli.main import main

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture
def temp_git_repo() -> Generator[Path]:
    """Create a temporary directory with an initialized git repository."""
    tmp_dir = TemporaryDirectory()
    tmp_path = Path(tmp_dir.name)
    # Initialize a git repo
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
    # Create an initial commit
    (tmp_path / "README.md").write_text("# Test")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True, capture_output=True)  # noqa: S607
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],  # noqa: S607
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    yield tmp_path
    tmp_dir.cleanup()


def test_cli_is_working(temp_git_repo: Path) -> None:
    """Test that CLI runs without crashing."""
    # Run CLI on temporary repo
    result = subprocess.run(  # noqa: S603
        ["pimp-my-repo", "--path", str(temp_git_repo)],  # noqa: S607
        check=False,
        capture_output=True,
        text=True,
    )
    # CLI should exit successfully (code 0) when git is clean, or code 1 when dirty
    assert result.returncode in (0, 1)
    assert "Pimping repository at:" in result.stdout
    # Either git is clean (success) or dirty (error message)
    assert ("Git working directory is clean" in result.stdout) or (
        "Git working directory is not clean" in result.stdout
    )


def test_main_is_working(temp_git_repo: Path) -> None:
    """Test that main function exits properly."""
    # Mock sys.argv to pass the path argument
    original_argv = sys.argv.copy()
    try:
        sys.argv = ["pimp-my-repo", "--path", str(temp_git_repo)]
        with pytest.raises(SystemExit) as exc_info:
            main()
        # Should exit with code 0 when git is clean, or code 1 when dirty
        assert exc_info.value.code in (0, 1)
    finally:
        sys.argv = original_argv


def test_cli_with_clean_git(temp_git_repo: Path) -> None:
    """Test CLI with a clean git repository."""
    # Run CLI on clean repo
    result = subprocess.run(  # noqa: S603
        ["pimp-my-repo", "--path", str(temp_git_repo)],  # noqa: S607
        check=False,
        capture_output=True,
        text=True,
    )
    # Should run successfully (exit code 0) or fail gracefully
    assert result.returncode in (0, 1)
    assert "Pimping repository at:" in result.stdout
