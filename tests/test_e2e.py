"""End-to-end tests for pimp-my-repo."""

from typing import TYPE_CHECKING

from loguru import logger
from rich.console import Console

from pimp_my_repo.cli.runner import run_boosts
from pimp_my_repo.core.result import BoostResultStatus
from pimp_my_repo.core.tools.subprocess import run_command

if TYPE_CHECKING:
    from pathlib import Path

    from pimp_my_repo.core.tools.repo import RepositoryController


def test_e2e_boosts_applied_then_idempotent(mock_repo: RepositoryController) -> None:
    """End-to-end: boosts apply on first run and make no changes on second run."""
    # Flat layout (no src/) so package=false — avoids project-install noise in sync --check.
    # requirements.txt ensures there are real external deps that sync_group bugs would wipe.
    mock_repo.add_and_commit(
        relative_path="main.py", content='def main() -> None:\n    print("hello")\n', message="Initial commit"
    )
    mock_repo.add_and_commit(relative_path="requirements.txt", content="iniconfig\n", message="Add requirements")

    console = Console(quiet=True)

    # --- Run 1: apply all boosts ---
    logger.info("E2E run 1: applying boosts...")
    run_result1 = run_boosts(mock_repo.path, console=console, log_to_file=False)

    # No boost should fail
    failed1 = [r for r in run_result1.results if r.status == "failed"]
    assert not failed1, f"Boosts failed on first run: {failed1}"

    by_name1 = {r.name: r.status for r in run_result1.results}
    assert by_name1["uv"] == BoostResultStatus.APPLIED

    assert mock_repo.is_clean()
    commits_after_run1 = mock_repo.commit_count()

    _assert_venv_fully_synced(mock_repo.path)

    # --- Run 2: no changes should be made ---
    logger.info("E2E run 2: verifying idempotency...")
    run_result2 = run_boosts(mock_repo.path, console=console, log_to_file=False)

    failed2 = [r for r in run_result2.results if r.status == "failed"]
    assert not failed2, f"Boosts failed on second run: {failed2}"

    commits_after_run2 = mock_repo.commit_count()
    assert commits_after_run2 == commits_after_run1, (
        f"Second run created {commits_after_run2 - commits_after_run1} unexpected commit(s)"
    )

    assert mock_repo.is_clean()
    _assert_venv_fully_synced(mock_repo.path)


def _assert_venv_fully_synced(repo_path: Path) -> None:
    logger.info(f"Checking venv sync state in {repo_path}...")
    result = run_command(["uv", "sync", "--all-groups", "--all-extras", "--check"], cwd=repo_path, check=False)
    logger.debug(f"uv sync --check stdout: {result.stdout!r}")
    logger.debug(f"uv sync --check stderr: {result.stderr!r}")
    assert result.returncode == 0, (
        f"uv sync --all-groups --all-extras --check failed — venv is not fully installed.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
