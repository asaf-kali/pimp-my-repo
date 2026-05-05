"""Run boosts with the live dashboard and log routing."""

from dataclasses import dataclass, field
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
    from pimp_my_repo.core.run_config import RunConfig


@dataclass
class BoostRunResult:
    """Result of a boost run, including the log file path if one was written."""

    results: list[BoostResult]
    log_path: Path | None


@dataclass
class ExecutionContext:
    """Internal PMR execution parameters — not user-facing, not passed to individual boosts."""

    boost_classes: list[type[Boost]] = field(default_factory=get_all_boosts)
    console: Console = field(default_factory=Console)
    log_to_file: bool = True


def run_boosts(run_config: RunConfig, context: ExecutionContext) -> BoostRunResult:
    """Run boosts on a repository and return results and the log file path (if any)."""
    return _run_boosts_with_dashboard(run_config=run_config, context=context)


def _run_boosts_with_dashboard(run_config: RunConfig, context: ExecutionContext) -> BoostRunResult:
    boost_names = [bc.get_name() for bc in context.boost_classes]
    dashboard = LiveDashboard(boost_names)

    logger.remove()
    logger.add(dashboard.add_log, level="INFO", format="<level>{level:<8}</level> {message}", colorize=True)

    log_path: Path | None = None
    if context.log_to_file:
        log_path = _log_file_path()
        logger.add(
            log_path,
            level=0,
            format="[{time:YYYY-MM-DD HH:mm:ss.SSS}] [{level:<4.4}] {message} [{name}] [{file}:{line}]",
            colorize=False,
        )
        context.console.print(f"[dim]Full log:[/dim] [cyan]{log_path}[/cyan]")

    results: list[BoostResult] = []

    with Live(dashboard, console=context.console, refresh_per_second=4):
        for result in execute_boosts(
            boost_classes=context.boost_classes,
            run_config=run_config,
            on_boost_start=dashboard.set_running,
        ):
            dashboard.set_result(result)
            results.append(result)

    return BoostRunResult(results=results, log_path=log_path)


def _log_file_path() -> Path:
    log_dir = Path.home() / ".local" / "state" / "pmr"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / f"pmr-{datetime.now(tz=UTC):%Y-%m-%d_%H-%M-%S}.log"
