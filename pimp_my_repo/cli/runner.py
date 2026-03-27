"""Run boosts with the live dashboard and log routing."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger
from rich.console import Console
from rich.live import Live

from pimp_my_repo.cli.ui.dashboard import LiveDashboard
from pimp_my_repo.core.booster import execute_boosts
from pimp_my_repo.core.registry import get_all_boosts

if TYPE_CHECKING:
    from pimp_my_repo.core.boosts.base import Boost
    from pimp_my_repo.core.result import BoostResult


@dataclass
class BoostRunResult:
    """Result of a boost run, including the log file path if one was written."""

    results: list[BoostResult]
    log_path: Path | None


def run_boosts(
    repo_path: Path,
    console: Console | None = None,
    boost_classes: list[type[Boost]] | None = None,
    log_to_file: bool = True,  # noqa: FBT001, FBT002
) -> BoostRunResult:
    """Run boosts on a repository and return results and the log file path (if any)."""
    if console is None:
        console = Console()
    if boost_classes is None:
        boost_classes = get_all_boosts()
    return _run_boosts_with_dashboard(
        repo_path=repo_path,
        boost_classes=boost_classes,
        console=console,
        log_to_file=log_to_file,
    )


def _run_boosts_with_dashboard(
    repo_path: Path,
    boost_classes: list[type[Boost]],
    console: Console,
    log_to_file: bool,  # noqa: FBT001
) -> BoostRunResult:
    boost_names = [bc.get_name() for bc in boost_classes]
    dashboard = LiveDashboard(boost_names)

    logger.remove()
    logger.add(dashboard.add_log, level="INFO", format="<level>{level:<8}</level> {message}", colorize=True)

    log_path: Path | None = None
    if log_to_file:
        log_path = _log_file_path()
        logger.add(
            log_path,
            level=0,
            format="[{time:YYYY-MM-DD HH:mm:ss.SSS}] [{level:<4.4}] {message} [{name}] [{file}:{line}]",
            colorize=False,
        )

    gen = execute_boosts(repo_path=repo_path, boost_classes=boost_classes)
    results: list[BoostResult] = []

    with Live(dashboard, console=console, refresh_per_second=10):
        for bc in boost_classes:
            dashboard.set_running(bc.get_name())
            result = next(gen)
            dashboard.set_result(result)
            results.append(result)

    return BoostRunResult(results=results, log_path=log_path)


def _log_file_path() -> Path:
    log_dir = Path.home() / ".local" / "state" / "pmr"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / f"pmr-{datetime.now(tz=UTC):%Y-%m-%d_%H-%M-%S}.log"
