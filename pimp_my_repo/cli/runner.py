"""Run boosts with the live dashboard and log routing."""

from typing import TYPE_CHECKING

from loguru import logger
from rich.console import Console
from rich.live import Live

from pimp_my_repo.cli.ui.dashboard import LiveDashboard
from pimp_my_repo.core.booster import execute_boosts
from pimp_my_repo.core.registry import get_all_boosts

if TYPE_CHECKING:
    from pathlib import Path

    from pimp_my_repo.core.boosts.base import Boost
    from pimp_my_repo.core.result import BoostResult


def run_boosts(
    repo_path: Path,
    console: Console | None = None,
    boost_classes: list[type[Boost]] | None = None,
    verbose: bool = False,  # noqa: FBT001, FBT002
) -> list[BoostResult]:
    """Run boosts on a repository and return results."""
    if console is None:
        console = Console()
    if boost_classes is None:
        boost_classes = get_all_boosts()
    return _run_boosts_with_dashboard(
        repo_path=repo_path,
        boost_classes=boost_classes,
        console=console,
        verbose=verbose,
    )


def _run_boosts_with_dashboard(
    repo_path: Path,
    boost_classes: list[type[Boost]],
    console: Console,
    verbose: bool,  # noqa: FBT001
) -> list[BoostResult]:
    boost_names = [bc.get_name() for bc in boost_classes]
    dashboard = LiveDashboard(boost_names)

    logger.remove()
    level = "DEBUG" if verbose else "INFO"
    logger.add(dashboard.add_log, level=level, format="<level>{level}</level>: {message}", colorize=True)

    gen = execute_boosts(repo_path=repo_path, boost_classes=boost_classes)
    results: list[BoostResult] = []

    with Live(dashboard, console=console, refresh_per_second=10):
        for bc in boost_classes:
            dashboard.set_running(bc.get_name())
            result = next(gen)
            dashboard.set_result(result)
            results.append(result)

    return results
