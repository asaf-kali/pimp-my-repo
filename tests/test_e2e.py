"""End-to-end tests for pimp-my-repo."""

from typing import TYPE_CHECKING

import pytest
from rich.console import Console

from pimp_my_repo.cli.main import run_boosts

if TYPE_CHECKING:
    from tests.repo_controller import RepositoryController


@pytest.mark.slow
def test_e2e_boosts_applied_then_idempotent(mock_repo: RepositoryController) -> None:
    """End-to-end: boosts apply on first run and make no changes on second run."""
    # Set up a simple Python project (no requirements.txt to stay on the minimal path)
    mock_repo.add_and_commit("src/main.py", 'def main() -> None:\n    print("hello")\n')

    console = Console(quiet=True)

    # --- Run 1: apply all boosts ---
    results1 = run_boosts(mock_repo.path, console=console)

    # No boost should fail
    failed1 = [r for r in results1 if r.status == "failed"]
    assert not failed1, f"Boosts failed on first run: {failed1}"

    # uv is the only implemented boost — it must be applied
    by_name1 = {r.name: r.status for r in results1}
    assert by_name1["uv"] == "applied"

    # Repo must be clean (all changes committed)
    assert mock_repo.is_clean()
    commits_after_run1 = mock_repo.commit_count()

    # --- Run 2: no changes should be made ---
    results2 = run_boosts(mock_repo.path, console=console)

    # No boost should fail
    failed2 = [r for r in results2 if r.status == "failed"]
    assert not failed2, f"Boosts failed on second run: {failed2}"

    # No new commits must have been created
    commits_after_run2 = mock_repo.commit_count()
    assert commits_after_run2 == commits_after_run1, (
        f"Second run created {commits_after_run2 - commits_after_run1} unexpected commit(s)"
    )

    # Repo must still be clean
    assert mock_repo.is_clean()
