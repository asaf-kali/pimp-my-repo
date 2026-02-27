"""CLI entry point for pimp-my-repo."""

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from loguru import logger
from rich.console import Console
from rich.table import Table
from typer import Exit

from pimp_my_repo.core.booster import execute_boosts
from pimp_my_repo.core.registry import get_all_boosts
from pimp_my_repo.core.tools.git import GitController

if TYPE_CHECKING:
    from pimp_my_repo.core.result import BoostResult

app = typer.Typer(
    name="pimp-my-repo",
    help="🧙🏼‍♂️ A CLI wizard designed to modernize your Python repositories",
)

DEFAULT_BRANCH_NAME = "feat/pmr"


def _validate_path(repo_path: Path, console: Console) -> None:
    """Validate that the repository path exists and is a directory."""
    if not repo_path.exists():
        console.print(f"[red]Error:[/red] Path does not exist: {repo_path}")
        raise Exit(code=1)

    if not repo_path.is_dir():
        console.print(f"[red]Error:[/red] Path is not a directory: {repo_path}")
        raise Exit(code=1)


def _setup_git(repo_path: Path, console: Console, branch_name: str | None = None) -> GitController:
    """Set up git manager and prepare the pmr branch."""
    git_manager = GitController(repo_path)

    # Check if git is clean
    console.print("[cyan]Checking git status...[/cyan]")
    try:
        if not git_manager.is_clean():
            console.print("[red]Error:[/red] Git working directory is not clean. Please commit or stash your changes.")
            raise Exit(code=1)
        console.print("[green]✓[/green] Git working directory is clean")
    except (subprocess.CalledProcessError, OSError) as e:
        logger.exception("Failed to check git status")
        console.print(f"[red]Error:[/red] Failed to check git status: {e}")
        raise Exit(code=1) from e

    # Create/switch to pmr branch
    branch_name = branch_name or DEFAULT_BRANCH_NAME
    console.print(f"[cyan]Creating/switching to branch: {branch_name}[/cyan]")
    try:
        git_manager.create_branch(branch_name)
        console.print(f"[green]✓[/green] On branch: {branch_name}")
    except (subprocess.CalledProcessError, OSError) as e:
        console.print(f"[red]Error:[/red] Failed to create/switch branch: {e}")
        raise Exit(code=1) from e

    return git_manager


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

    # Setup git
    git_manager = _setup_git(repo_path, console)

    # Initialize boosts
    boost_classes = get_all_boosts()
    console.print(f"[cyan]Found {len(boost_classes)} boosts[/cyan]")

    # Execute boosts
    results = execute_boosts(boost_classes, repo_path, git_manager, console)

    # Print summary
    _print_summary(results, console)


def run_boosts(repo_path: Path, console: Console | None = None) -> list[BoostResult]:
    """Run all boosts on a repository and return results."""
    if console is None:
        console = Console()
    git_manager = _setup_git(repo_path, console)
    boost_classes = get_all_boosts()
    return execute_boosts(boost_classes, repo_path, git_manager, console)


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
