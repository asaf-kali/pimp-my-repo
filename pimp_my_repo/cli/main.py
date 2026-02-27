"""CLI entry point for pimp-my-repo."""

from pathlib import Path
from typing import TYPE_CHECKING

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TaskID, TextColumn
from rich.table import Table
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


_PROGRESS_DESCRIPTIONS = {
    "applied": "[green]✓ {name} applied[/green]",
    "skipped": "[yellow]⊘ {name} skipped: {message}[/yellow]",
    "failed": "[red]✗ {name} failed[/red]",
}


@app.command()
def run(
    path: str = typer.Option(
        ".",
        "--path",
        "-p",
        help="Path to the repository to pimp",
    ),
    wizard: bool = typer.Option(  # noqa: FBT001
        False,  # noqa: FBT003
        "--wizard",
        "-w",
        help="Enable interactive wizard mode (not implemented yet)",
    ),
) -> None:
    """Pimp a repository."""
    console = Console()

    if wizard:
        console.print("[yellow]Wizard mode is not yet implemented[/yellow]")
        raise Exit(code=1)

    repo_path = Path(path).resolve()

    # Pre-flight checks
    console.print(f"[bold]Pimping repository at: {repo_path}[/bold]")
    _validate_path(repo_path, console)

    # Initialize boosts
    boost_classes = get_all_boosts()
    console.print(f"[cyan]Found {len(boost_classes)} boosts[/cyan]")

    # Execute boosts
    try:
        results = run_boosts(repo_path=repo_path, console=console)
    except Exception as e:
        console.print("[red]An error occurred while running boosts[/red]")
        console.print(f"[red]Error:[/red] {e}")
        raise Exit(code=1) from e

    # Print summary
    _print_summary(results, console)


def run_boosts(repo_path: Path, console: Console | None = None) -> list[BoostResult]:
    """Run all boosts on a repository and return results."""
    if console is None:
        console = Console()
    boost_classes = get_all_boosts()
    return _run_boosts_with_progress(repo_path=repo_path, boost_classes=boost_classes, console=console)


def _validate_path(repo_path: Path, console: Console) -> None:
    """Validate that the repository path exists and is a directory."""
    if not repo_path.exists():
        console.print(f"[red]Error:[/red] Path does not exist: {repo_path}")
        raise Exit(code=1)

    if not repo_path.is_dir():
        console.print(f"[red]Error:[/red] Path is not a directory: {repo_path}")
        raise Exit(code=1)


def _update_progress(progress: Progress, task_id: TaskID, result: BoostResult) -> None:
    template = _PROGRESS_DESCRIPTIONS.get(result.status, "{name}: {message}")
    description = template.format(name=result.name, message=result.message)
    progress.update(task_id=task_id, description=description)


def _run_boosts_with_progress(
    repo_path: Path,
    boost_classes: list[type[Boost]],
    console: Console,
) -> list[BoostResult]:
    """Drive the execute_boosts generator, rendering live progress for each result."""
    results: list[BoostResult] = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task_ids = [progress.add_task(description=f"Processing {bc.get_name()}...", total=None) for bc in boost_classes]
        for task_id, result in zip(
            task_ids, execute_boosts(repo_path=repo_path, boost_classes=boost_classes), strict=True
        ):
            _update_progress(progress=progress, task_id=task_id, result=result)
            results.append(result)
    return results


def _print_summary(results: list[BoostResult], console: Console) -> None:
    """Print summary table of boost execution results."""
    console.print("\n[bold]Summary:[/bold]")
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Boost", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Message")

    for result in results:
        status_style = {
            "applied": "[green]✓ Applied[/green]",
            "skipped": "[yellow]⊘ Skipped[/yellow]",
            "failed": "[red]✗ Failed[/red]",
        }.get(result.status, result.status)
        table.add_row(result.name, status_style, result.message)

    console.print(table)

    applied_count = sum(1 for r in results if r.status == "applied")
    if applied_count > 0:
        console.print(f"\n[green]✓ Successfully applied {applied_count} boost(s)[/green]")
    else:
        console.print("\n[yellow]No boosts were applied[/yellow]")


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
