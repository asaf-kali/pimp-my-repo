"""CLI entry point for pimp-my-repo."""

from pathlib import Path
from typing import TYPE_CHECKING

import typer
from rich.console import Console
from typer import Exit

from pimp_my_repo.cli.runner import run_boosts
from pimp_my_repo.core.registry import get_all_boosts, get_opt_in_boosts

if TYPE_CHECKING:
    from pimp_my_repo.core.boosts.base import Boost
    from pimp_my_repo.core.result import BoostResult

app = typer.Typer(
    name="pimp-my-repo",
    help="🧙🏼‍♂️ A CLI wizard designed to modernize your Python repositories",
)

_PATH_ARG = typer.Option(".", "--path", "-p", help="Path to the repository to pimp")
_ONLY_ARG = typer.Option([], "--only", help="Run only these boost(s) (repeatable)")
_SKIP_ARG = typer.Option([], "--skip", help="Skip these boost(s) (repeatable)")
_LIST_ARG = typer.Option(False, "--list", help="List available boosts and exit")  # noqa: FBT003
_NO_LOG_FILE_ARG = typer.Option(False, "--no-log-file", help="Disable writing logs to file")  # noqa: FBT003


@app.command()
def run(
    path: str = _PATH_ARG,
    only: list[str] = _ONLY_ARG,
    skip: list[str] = _SKIP_ARG,
    list_boosts: bool = _LIST_ARG,  # noqa: FBT001
    no_log_file: bool = _NO_LOG_FILE_ARG,  # noqa: FBT001
) -> None:
    """Apply PMR boosts to a repository."""
    console = Console()

    boost_classes = _resolve_boosts(only=only, skip=skip, list_boosts=list_boosts, console=console)

    repo_path = Path(path).resolve()
    console.print(f"[bold]Boosting repository at:[/bold] [cyan]{repo_path}[/cyan]")
    _validate_path(repo_path, console)

    run_result = run_boosts(
        repo_path=repo_path, console=console, boost_classes=boost_classes, log_to_file=not no_log_file
    )
    _print_summary(run_result.results, console)


def _resolve_boosts(
    only: list[str],
    skip: list[str],
    list_boosts: bool,  # noqa: FBT001
    console: Console,
) -> list[type[Boost]]:
    default_boosts = get_all_boosts()
    opt_in_boosts = get_opt_in_boosts()
    all_known = default_boosts + opt_in_boosts
    name_to_boost = {bc.get_name(): bc for bc in all_known}

    if list_boosts:
        console.print("[bold]Available boosts:[/bold]")
        for bc in default_boosts:
            console.print(f"  ✨ {bc.get_name()}")
        for bc in opt_in_boosts:
            console.print(f"  ✨ {bc.get_name()} [dim](opt-in)[/dim]")
        raise Exit(0)

    if only and skip:
        console.print("[red]Error:[/red] --only and --skip are mutually exclusive")
        raise Exit(1)

    unknown = [n for n in (only or skip) if n not in name_to_boost]
    if unknown:
        console.print(f"[red]Error:[/red] Unknown boost(s): {', '.join(unknown)}")
        console.print(f"Valid boosts: {', '.join(name_to_boost)}")
        raise Exit(1)

    if only:
        return [name_to_boost[n] for n in only]
    if skip:
        skip_set = set(skip)
        return [bc for bc in default_boosts if bc.get_name() not in skip_set]
    return default_boosts


def _validate_path(repo_path: Path, console: Console) -> None:
    if not repo_path.exists():
        console.print(f"[red]Error:[/red] Path does not exist: {repo_path}")
        raise Exit(code=1)

    if not repo_path.is_dir():
        console.print(f"[red]Error:[/red] Path is not a directory: {repo_path}")
        raise Exit(code=1)


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
    if failed:
        raise Exit(1)


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
