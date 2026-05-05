import contextlib
from typing import TYPE_CHECKING

from loguru import logger

from pimp_my_repo import __version__
from pimp_my_repo.core.boosts.base import Boost, BoostSkipped, BoostStartCallback
from pimp_my_repo.core.result import BoostResult, BoostResultStatus
from pimp_my_repo.core.tools.boost_tools import BoostTools

if TYPE_CHECKING:
    from collections.abc import Generator, Iterator
    from pathlib import Path

    from pimp_my_repo.core.run_config import RunConfig
    from pimp_my_repo.core.tools.repo import RepositoryController


@contextlib.contextmanager
def _git_revert_context(repo_controller: RepositoryController) -> Generator[str]:
    """Context manager to revert git changes."""
    sha_before = repo_controller.get_current_commit_sha()
    try:
        yield sha_before
    except BaseException:
        logger.debug(f"Reverting git changes to {sha_before}")
        repo_controller.reset_hard(sha_before)
        raise


def _run_boost(
    boost: Boost,
    boost_name: str,
    repo_controller: RepositoryController,
) -> BoostResult:
    """Process a single boost and return result.

    Captures the git HEAD before calling apply().  On any non-skip failure,
    resets hard back to that ref so the repo is left in a clean state.
    """
    logger.info(f"Running boost '{boost_name}'")
    try:
        with _git_revert_context(repo_controller) as sha_before_apply:
            boost.apply()
            sha_after_apply = repo_controller.get_current_commit_sha()
            commits_made_during_apply = sha_before_apply != sha_after_apply
            committed = repo_controller.commit(boost.commit_message())
    except BoostSkipped as e:
        logger.info(f"Boost '{boost_name}' skipped: {e.reason}")
        return BoostResult(name=boost_name, status=BoostResultStatus.SKIPPED, message=e.reason)

    if commits_made_during_apply or committed:
        logger.info(f"Boost '{boost_name}' applied successfully")
        return BoostResult(name=boost_name, status=BoostResultStatus.APPLIED, message="Success")

    logger.info(f"Boost '{boost_name}' made no changes")
    return BoostResult(name=boost_name, status=BoostResultStatus.SKIPPED, message="No changes to commit")


def _run_boost_class(
    boost_class: type[Boost],
    boost_tools: BoostTools,
    repo_controller: RepositoryController,
    run_config: RunConfig | None = None,
) -> BoostResult:
    boost_name = boost_class.get_name()
    try:
        boost = boost_class(boost_tools, run_config=run_config)
        return _run_boost(boost=boost, boost_name=boost_name, repo_controller=repo_controller)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error applying '{boost_name}' boost: {e}")
        logger.debug(f"Error applying '{boost_name}' boost", exc_info=True)
        return BoostResult(name=boost_name, status=BoostResultStatus.FAILED, message=str(e))


def execute_boosts(
    repo_path: Path,
    boost_classes: list[type[Boost]],
    on_boost_start: BoostStartCallback | None = None,
    branch: str | None = None,
    run_config: RunConfig | None = None,
) -> Iterator[BoostResult]:
    """Execute all boosts and yield results as they complete."""
    logger.info(f"Running PMR [v{__version__}] boosts on repository: [{repo_path}]")
    boost_tools = BoostTools.create(repo_path=repo_path)
    init_kwargs = {"branch_name": branch} if branch is not None else {}
    boost_tools.git.init_pmr(**init_kwargs)
    logger.info(f"Found {len(boost_classes)} boosts to run: {[bc.get_name() for bc in boost_classes]}")
    for bc in boost_classes:
        if on_boost_start:
            on_boost_start(bc.get_name())
        yield _run_boost_class(
            boost_class=bc, boost_tools=boost_tools, repo_controller=boost_tools.git, run_config=run_config
        )
    logger.info("Finished running PMR boosts")
