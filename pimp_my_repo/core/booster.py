__author__ = "Asaf Kali"
__date__ = "27/02/2026"
__copyright__ = "Copyright (C) 2026 Duality Technologies (https://www.dualitytech.com)"

import contextlib
import subprocess
from typing import TYPE_CHECKING

from loguru import logger

from pimp_my_repo.core.boosts.base import Boost, BoostSkippedError
from pimp_my_repo.core.result import BoostResult
from pimp_my_repo.core.tools.boost_tools import BoostTools

if TYPE_CHECKING:
    from collections.abc import Generator, Iterator
    from pathlib import Path

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


def _run_boost(
    boost: Boost,
    boost_name: str,
    git_manager: GitController,
) -> BoostResult:
    """Process a single boost and return result.

    Captures the git HEAD before calling apply().  On any non-skip failure,
    resets hard back to that ref so the repo is left in a clean state.
    """
    try:
        with _git_revert_context(git_manager) as sha_before_apply:
            boost.apply()
            sha_after_apply = git_manager.get_current_commit_sha()
            commits_made_during_apply = sha_before_apply != sha_after_apply
            committed = git_manager.commit(boost.commit_message())
    except BoostSkippedError as e:
        return BoostResult(name=boost_name, status="skipped", message=e.reason)

    if commits_made_during_apply or committed:
        return BoostResult(name=boost_name, status="applied", message="Success")

    return BoostResult(name=boost_name, status="skipped", message="No changes to commit")


def _run_boost_class(
    boost_class: type[Boost],
    boost_tools: BoostTools,
    git_manager: GitController,
) -> BoostResult:
    boost_name = boost_class.get_name()
    try:
        boost = boost_class(boost_tools)
        return _run_boost(boost=boost, boost_name=boost_name, git_manager=git_manager)
    except (subprocess.CalledProcessError, OSError) as e:
        logger.exception(f"Error applying {boost_name} boost")
        return BoostResult(name=boost_name, status="failed", message=str(e))


def execute_boosts(
    repo_path: Path,
    boost_classes: list[type[Boost]],
) -> Iterator[BoostResult]:
    """Execute all boosts and yield results as they complete."""
    boost_tools = BoostTools.create(repo_path=repo_path)
    boost_tools.git.init_pmr()
    for bc in boost_classes:
        yield _run_boost_class(boost_class=bc, boost_tools=boost_tools, git_manager=boost_tools.git)
