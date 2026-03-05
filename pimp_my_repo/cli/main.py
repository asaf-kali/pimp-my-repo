"""CLI entry point for pimp-my-repo."""

import sys
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from loguru import logger
from rich.console import Console
from typer import Exit

from pimp_my_repo.core.booster import execute_boosts
from pimp_my_repo.core.registry import get_all_boosts

if TYPE_CHECKING:
    from pimp_my_repo.core.boosts.base import Boost
    from pimp_my_repo.core.result import BoostResult

app = typer.Typer(
    name="pimp-my-repo",
    help="🧙🏼‍♂️ A CLI wizard designed to modernize your Python repositories",
)

_STATUS_CONFIG: dict[str, tuple[str, str]] = {
    "applied": ("✓", "green"),
    "skipped": ("⊘", "yellow"),
    "failed": ("✗", "red"),
}


def _setup_logging(*, verbose: bool) -> None:
    logger.remove()
    level = "DEBUG" if verbose else "WARNING"
    logger.add(sys.stderr, level=level, format="<level>{level}</level>: {message}", colorize=True)


@app.command()
def run(
    path: str = typer.Option(".", "--path", "-p", help="Path to the repository to pimp"),
    verbose: bool = typer.Option(  # noqa: FBT001
        False,  # noqa: FBT003
        "--verbose",
        "-v",
        help="Show detailed progress logs from each boost",
    ),
) -> None:
    """Pimp a repository."""
    _setup_logging(verbose=verbose)
    console = Console()

    repo_path = Path(path).resolve()
    console.print(f"[bold]Pimping repository at:[/bold] [cyan]{repo_path}[/cyan]")
    _validate_path(repo_path, console)

    results = run_boosts(repo_path=repo_path, console=console)
    _print_summary(results, console)


def run_boosts(repo_path: Path, console: Console | None = None) -> list[BoostResult]:
    """Run all boosts on a repository and return results."""
    if console is None:
        console = Console()
    boost_classes = get_all_boosts()
    return _run_boosts_with_progress(repo_path=repo_path, boost_classes=boost_classes, console=console)


def _validate_path(repo_path: Path, console: Console) -> None:
    if not repo_path.exists():
        console.print(f"[red]Error:[/red] Path does not exist: {repo_path}")
        raise Exit(code=1)

    if not repo_path.is_dir():
        console.print(f"[red]Error:[/red] Path is not a directory: {repo_path}")
        raise Exit(code=1)


def _print_boost_result(console: Console, result: BoostResult) -> None:
    icon, style = _STATUS_CONFIG.get(result.status, ("?", "white"))
    name = f"[cyan]{result.name:<12}[/cyan]"
    if result.status == "applied":
        console.print(f"  [{style}]{icon}[/{style}] {name}")
    elif result.status == "skipped":
        console.print(f"  [{style}]{icon}[/{style}] {name}  [dim]{result.message}[/dim]")
    else:
        short_msg = result.message.splitlines()[0][:80]
        console.print(f"  [{style}]{icon}[/{style}] {name}  [{style}]{short_msg}[/{style}]")


def _run_boosts_with_progress(
    repo_path: Path,
    boost_classes: list[type[Boost]],
    console: Console,
) -> list[BoostResult]:
    """Run each boost with a per-boost spinner; print each result as it completes."""
    gen = execute_boosts(repo_path=repo_path, boost_classes=boost_classes)
    results: list[BoostResult] = []
    for bc in boost_classes:
        with console.status(f"  [dim]running[/dim] [cyan]{bc.get_name()}[/cyan]…"):
            result = next(gen)
        _print_boost_result(console, result)
        results.append(result)
    return results


def _print_summary(results: list[BoostResult], console: Console) -> None:
    applied = sum(1 for r in results if r.status == "applied")
    failed = sum(1 for r in results if r.status == "failed")
    console.print()
    if failed:
        console.print(f"[red]✗ {failed} boost(s) failed[/red]  ", end="")
    if applied:
        console.print(f"[green]✓ {applied} boost(s) applied[/green]")
    else:
        console.print("[yellow]No boosts applied[/yellow]")


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
