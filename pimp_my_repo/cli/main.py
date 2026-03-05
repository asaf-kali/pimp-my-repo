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


_PATH_ARG = typer.Option(".", "--path", "-p", help="Path to the repository to pimp")
_VERBOSE_ARG = typer.Option(
    False,  # noqa: FBT003
    "--verbose",
    "-v",
    help="Show detailed progress logs from each boost",
)
_ONLY_ARG = typer.Option([], "--only", help="Run only these boost(s) (repeatable)")
_SKIP_ARG = typer.Option([], "--skip", help="Skip these boost(s) (repeatable)")
_LIST_ARG = typer.Option(False, "--list", help="List available boosts and exit")  # noqa: FBT003


@app.command()
def run(
    path: str = _PATH_ARG,
    verbose: bool = _VERBOSE_ARG,  # noqa: FBT001
    only: list[str] = _ONLY_ARG,
    skip: list[str] = _SKIP_ARG,
    list_boosts: bool = _LIST_ARG,  # noqa: FBT001
) -> None:
    """Pimp a repository."""
    _setup_logging(verbose=verbose)
    console = Console()

    boost_classes = _resolve_boosts(only=only, skip=skip, list_boosts=list_boosts, console=console)

    repo_path = Path(path).resolve()
    console.print(f"[bold]Pimping repository at:[/bold] [cyan]{repo_path}[/cyan]")
    _validate_path(repo_path, console)

    results = run_boosts(repo_path=repo_path, console=console, boost_classes=boost_classes)
    _print_summary(results, console)


def _resolve_boosts(
    only: list[str],
    skip: list[str],
    list_boosts: bool,  # noqa: FBT001
    console: Console,
) -> list[type[Boost]]:
    """Resolve which boosts to run based on --only, --skip, and --list flags."""
    all_boosts = get_all_boosts()
    valid_names = {bc.get_name(): bc for bc in all_boosts}

    if list_boosts:
        console.print("[bold]Available boosts:[/bold]")
        for name in valid_names:
            console.print(f"  {name}")
        raise Exit(0)

    if only and skip:
        console.print("[red]Error:[/red] --only and --skip are mutually exclusive")
        raise Exit(1)

    unknown = [n for n in (only or skip) if n not in valid_names]
    if unknown:
        console.print(f"[red]Error:[/red] Unknown boost(s): {', '.join(unknown)}")
        console.print(f"Valid boosts: {', '.join(valid_names)}")
        raise Exit(1)

    if only:
        return [valid_names[n] for n in only]
    if skip:
        skip_set = set(skip)
        return [bc for bc in all_boosts if bc.get_name() not in skip_set]
    return all_boosts


def run_boosts(
    repo_path: Path,
    console: Console | None = None,
    boost_classes: list[type[Boost]] | None = None,
) -> list[BoostResult]:
    """Run boosts on a repository and return results."""
    if console is None:
        console = Console()
    if boost_classes is None:
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
