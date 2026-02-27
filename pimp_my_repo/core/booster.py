__author__ = "Asaf Kali"
__date__ = "27/02/2026"
__copyright__ = "Copyright (C) 2026 Duality Technologies (https://www.dualitytech.com)"

import contextlib
import subprocess
from typing import TYPE_CHECKING

from loguru import logger
from rich.progress import Progress, SpinnerColumn, TaskID, TextColumn

from pimp_my_repo.core.boosts.base import Boost, BoostSkippedError
from pimp_my_repo.core.result import BoostResult
from pimp_my_repo.core.tools.boost_tools import BoostTools

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from rich.console import Console

    from pimp_my_repo.core.tools.git import GitController


@contextlib.contextmanager
def _git_revert_context(git_manager: GitController) -> Generator[str]:
    """Context manager to revert git changes."""
    sha_before = git_manager.get_current_commit_sha()
    try:
        yield sha_before
    except:
        logger.debug(f"Reverting git changes to {sha_before}")
        git_manager.reset_hard(sha_before)
        raise


def _process_boost(
    boost: Boost,
    boost_name: str,
    git_manager: GitController,
    progress: Progress,
    task_id: TaskID,
) -> BoostResult:
    """Process a single boost and return result.

    Captures the git HEAD before calling apply().  On any non-skip failure,
    resets hard back to that ref so the repo is left in a clean state.
    """
    try:
        with _git_revert_context(git_manager) as sha_before_apply:
            boost.apply()
            sha_after_apply = git_manager.get_current_commit_sha()
            # Check if any commits were made during apply()
            commits_made_during_apply = sha_before_apply != sha_after_apply
            committed = git_manager.commit(boost.commit_message())
    except BoostSkippedError as e:
        progress.update(task_id, description=f"[yellow]⊘ Skipping {boost_name}: {e.reason}[/yellow]")
        return BoostResult(name=boost_name, status="skipped", message=e.reason)
    except Exception as e:  # noqa: BLE001
        logger.exception(f"Error applying {boost_name} boost")
        progress.update(task_id, description=f"[red]✗ {boost_name} failed[/red]")
        return BoostResult(name=boost_name, status="failed", message=str(e))

    # If commits were made during apply() OR final commit succeeded, mark as applied
    if commits_made_during_apply or committed:
        progress.update(task_id, description=f"[green]✓ {boost_name} applied[/green]")
        return BoostResult(name=boost_name, status="applied", message="Success")

    progress.update(task_id, description=f"[yellow]⊘ Skipping {boost_name}: no changes[/yellow]")
    return BoostResult(name=boost_name, status="skipped", message="No changes to commit")


def execute_boosts(
    boost_classes: list[type[Boost]],
    repo_path: Path,
    git_manager: GitController,
    console: Console,
) -> list[BoostResult]:
    """Execute all boosts and return results."""
    results: list[BoostResult] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        boost_tools = BoostTools.create(repo_path)
        for boost_class in boost_classes:
            boost_name = boost_class.get_name()
            task_id = progress.add_task(f"Processing {boost_name} boost...", total=None)

            try:
                boost = boost_class(boost_tools)
                result = _process_boost(boost, boost_name, git_manager, progress, task_id)
                results.append(result)

            except (subprocess.CalledProcessError, OSError) as e:
                logger.exception(f"Error processing {boost_name} boost")
                progress.update(task_id, description=f"[red]✗ {boost_name} failed[/red]")
                results.append(BoostResult(name=boost_name, status="failed", message=str(e)))

    return results
