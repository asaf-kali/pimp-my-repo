"""CLI entry point for pimp-my-repo."""

import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from loguru import logger
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from typer import Exit

from pimp_my_repo.core.boost import Boost, get_all_boosts
from pimp_my_repo.core.git import GitManager
from pimp_my_repo.core.state import StateManager
from pimp_my_repo.models.state import BoostState, ProjectState

if TYPE_CHECKING:
    from rich.progress import TaskID

app = typer.Typer(
    name="pimp-my-repo",
    help="🧙🏼‍♂️ A CLI wizard designed to modernize your Python repositories",
)


def _validate_path(repo_path: Path, console: Console) -> None:
    """Validate that the repository path exists and is a directory."""
    if not repo_path.exists():
        console.print(f"[red]Error:[/red] Path does not exist: {repo_path}")
        raise Exit(code=1)

    if not repo_path.is_dir():
        console.print(f"[red]Error:[/red] Path is not a directory: {repo_path}")
        raise Exit(code=1)


def _setup_git_and_state(repo_path: Path, console: Console) -> tuple[GitManager, ProjectState, StateManager, str]:
    """Set up git manager, state, and project key."""
    git_manager = GitManager(repo_path)

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

    # Get origin URL or use path as fallback
    try:
        origin_url = git_manager.get_origin_url()
    except (subprocess.CalledProcessError, OSError) as e:
        logger.debug(f"Failed to get origin URL: {e}")
        origin_url = None
    project_key = origin_url if origin_url else str(repo_path)
    console.print(f"[cyan]Project key: {project_key}[/cyan]")

    # Load or create state
    state_manager = StateManager()
    state = state_manager.load_state(project_key)

    if state is None:
        state = ProjectState(
            project_key=project_key,
            repo_path=str(repo_path),
            branch_name="pmr",
        )
        console.print("[green]✓[/green] Created new state")
    else:
        console.print("[green]✓[/green] Loaded existing state")

    # Create/switch to pmr branch
    console.print(f"[cyan]Creating/switching to branch: {state.branch_name}[/cyan]")
    try:
        git_manager.create_branch(state.branch_name)
        console.print(f"[green]✓[/green] On branch: {state.branch_name}")
    except (subprocess.CalledProcessError, OSError) as e:
        console.print(f"[red]Error:[/red] Failed to create/switch branch: {e}")
        raise Exit(code=1) from e

    return git_manager, state, state_manager, project_key


def _process_boost(  # noqa: PLR0913
    boost: Boost,
    boost_name: str,
    state: ProjectState,
    git_manager: GitManager,
    progress: Progress,
    task_id: TaskID,
) -> dict[str, str]:
    """Process a single boost and return result."""
    boost_state = state.boosts.get(boost_name)
    if boost_state and boost_state.applied:
        progress.update(task_id, description=f"[yellow]Skipping {boost_name} (already applied)[/yellow]")
        return {"boost": boost_name, "status": "skipped", "message": "Already applied"}

    # Check preconditions
    try:
        if not boost.check_preconditions():
            progress.update(task_id, description=f"[yellow]Skipping {boost_name} (preconditions not met)[/yellow]")
            return {"boost": boost_name, "status": "skipped", "message": "Preconditions not met"}
    except NotImplementedError:
        progress.update(task_id, description=f"[yellow]Skipping {boost_name} (not implemented)[/yellow]")
        return {"boost": boost_name, "status": "skipped", "message": "Not implemented"}

    # Apply boost
    try:
        boost.apply()
    except NotImplementedError:
        progress.update(task_id, description=f"[yellow]Skipping {boost_name} (not implemented)[/yellow]")
        return {"boost": boost_name, "status": "skipped", "message": "Not implemented"}

    # Verify boost
    verified = False
    try:
        verified = boost.verify()
    except NotImplementedError:
        logger.debug(f"Verification not implemented for {boost_name}")

    # Commit changes
    commit_message = boost.commit_message()
    commit_sha = None
    try:
        git_manager.commit(commit_message)
        try:
            commit_sha = git_manager.get_current_commit_sha()
        except (subprocess.CalledProcessError, OSError) as e:
            logger.debug(f"Failed to get commit SHA for {boost_name}: {e}")
            # Continue without commit SHA
    except (subprocess.CalledProcessError, OSError):
        logger.exception(f"Failed to commit changes for {boost_name}")
        # Continue without commit SHA - boost was still applied

    # Update state
    now = datetime.now(UTC)
    boost_state = BoostState(
        name=boost_name,
        applied_at=now,
        verified_at=now if verified else None,
        commit_sha=commit_sha,
    )
    state.boosts[boost_name] = boost_state
    state.updated_at = now

    progress.update(task_id, description=f"[green]✓ {boost_name} applied[/green]")
    return {"boost": boost_name, "status": "applied", "message": "Success"}


def _execute_boosts(  # noqa: PLR0913
    boost_classes: list[type[Boost]],
    repo_path: Path,
    state: ProjectState,
    git_manager: GitManager,
    state_manager: StateManager,
    project_key: str,
    console: Console,
) -> list[dict[str, str]]:
    """Execute all boosts and return results."""
    results: list[dict[str, str]] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        for boost_class in boost_classes:
            boost_name = boost_class.get_name()
            task_id = progress.add_task(f"Processing {boost_name} boost...", total=None)

            try:
                boost = boost_class(repo_path)
                result = _process_boost(boost, boost_name, state, git_manager, progress, task_id)
                results.append(result)

                # Save state after each boost
                state_manager.save_state(project_key, state)

            except (NotImplementedError, subprocess.CalledProcessError, OSError) as e:
                logger.exception(f"Error processing {boost_name} boost")
                progress.update(task_id, description=f"[red]✗ {boost_name} failed[/red]")
                results.append({"boost": boost_name, "status": "failed", "message": str(e)})

    return results


def _print_summary(results: list[dict[str, str]], console: Console) -> None:
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
        }.get(result["status"], result["status"])
        table.add_row(result["boost"], status_style, result["message"])

    console.print(table)

    # Final message
    applied_count = sum(1 for r in results if r["status"] == "applied")
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

    # Setup git and state
    git_manager, state, state_manager, project_key = _setup_git_and_state(repo_path, console)

    # Initialize boosts
    boost_classes = get_all_boosts()
    console.print(f"[cyan]Found {len(boost_classes)} boosts[/cyan]")

    # Execute boosts
    results = _execute_boosts(boost_classes, repo_path, state, git_manager, state_manager, project_key, console)

    # Print summary
    _print_summary(results, console)


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
