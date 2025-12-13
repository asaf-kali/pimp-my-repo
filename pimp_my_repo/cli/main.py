"""CLI entry point for pimp-my-repo."""

import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from loguru import logger
from typer import Exit

from pimp_my_repo.core.boost import Boost, get_all_boosts
from pimp_my_repo.core.detector import detect_all
from pimp_my_repo.core.git import GitManager
from pimp_my_repo.core.state import StateManager
from pimp_my_repo.models.state import BoostState, State
from pimp_my_repo.ui import RichUI

if TYPE_CHECKING:
    from rich.progress import Progress, TaskID

app = typer.Typer(
    name="pimp-my-repo",
    help="🧙🏼‍♂️ A CLI wizard designed to modernize your Python repositories",
)


def _validate_path(repo_path: Path, ui: RichUI) -> None:
    """Validate that the repository path exists and is a directory."""
    if not repo_path.exists():
        ui.print_error(f"Path does not exist: {repo_path}")
        raise Exit(code=1)

    if not repo_path.is_dir():
        ui.print_error(f"Path is not a directory: {repo_path}")
        raise Exit(code=1)


def _setup_git_and_state(repo_path: Path, ui: RichUI) -> tuple[GitManager, State, StateManager, str]:
    """Set up git manager, state, and project key."""
    git_manager = GitManager(repo_path)

    # Check if git is clean
    ui.print_cyan("Checking git status...")
    try:
        if not git_manager.is_clean():
            ui.print_error("Git working directory is not clean. Please commit or stash your changes.")
            raise Exit(code=1)
        ui.print_success("Git working directory is clean")
    except (subprocess.CalledProcessError, OSError) as e:
        logger.exception("Failed to check git status")
        ui.print_error(f"Failed to check git status: {e}")
        raise Exit(code=1) from e

    # Get origin URL or use path as fallback
    try:
        origin_url = git_manager.get_origin_url()
    except (subprocess.CalledProcessError, OSError) as e:
        logger.debug(f"Failed to get origin URL: {e}")
        origin_url = None
    project_key = origin_url if origin_url else str(repo_path)
    ui.print_cyan(f"Project key: {project_key}")

    # Load or create state
    state_manager = StateManager()
    state = state_manager.load_state(project_key)

    if state is None:
        state = State(
            project_key=project_key,
            repo_path=str(repo_path),
            branch_name="pmr",
        )
        ui.print_success("Created new state")
    else:
        ui.print_success("Loaded existing state")

    # Create/switch to pmr branch
    ui.print_cyan(f"Creating/switching to branch: {state.branch_name}")
    try:
        git_manager.create_branch(state.branch_name)
        ui.print_success(f"On branch: {state.branch_name}")
    except (subprocess.CalledProcessError, OSError) as e:
        ui.print_error(f"Failed to create/switch branch: {e}")
        raise Exit(code=1) from e

    return git_manager, state, state_manager, project_key


def _process_boost(  # noqa: PLR0913
    boost: Boost,
    boost_name: str,
    state: State,
    git_manager: GitManager,
    ui: RichUI,
    progress: Progress,
    task_id: TaskID,
) -> dict[str, str]:
    """Process a single boost and return result."""
    boost_state = state.boosts.get(boost_name)
    if boost_state and boost_state.applied:
        ui.update_task(progress, task_id, f"[yellow]Skipping {boost_name} (already applied)[/yellow]")
        return {"boost": boost_name, "status": "skipped", "message": "Already applied"}

    # Check preconditions
    try:
        if not boost.check_preconditions():
            ui.update_task(progress, task_id, f"[yellow]Skipping {boost_name} (preconditions not met)[/yellow]")
            return {"boost": boost_name, "status": "skipped", "message": "Preconditions not met"}
    except NotImplementedError:
        ui.update_task(progress, task_id, f"[yellow]Skipping {boost_name} (not implemented)[/yellow]")
        return {"boost": boost_name, "status": "skipped", "message": "Not implemented"}

    # Apply boost
    try:
        boost.apply()
    except NotImplementedError:
        ui.update_task(progress, task_id, f"[yellow]Skipping {boost_name} (not implemented)[/yellow]")
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
        applied=True,
        applied_at=now,
        verified=verified,
        verified_at=now if verified else None,
        commit_sha=commit_sha,
    )
    state.boosts[boost_name] = boost_state
    state.updated_at = now

    ui.update_task(progress, task_id, f"[green]✓ {boost_name} applied[/green]")
    return {"boost": boost_name, "status": "applied", "message": "Success"}


def _execute_boosts(  # noqa: PLR0913
    boost_classes: list[type[Boost]],
    repo_path: Path,
    state: State,
    git_manager: GitManager,
    state_manager: StateManager,
    project_key: str,
    ui: RichUI,
) -> list[dict[str, str]]:
    """Execute all boosts and return results."""
    results: list[dict[str, str]] = []

    with ui.create_progress_context() as progress:
        for boost_class in boost_classes:
            boost_name = boost_class.get_name()
            task_id = ui.create_task(progress, f"Processing {boost_name} boost...")

            try:
                boost = boost_class(repo_path)
                result = _process_boost(boost, boost_name, state, git_manager, ui, progress, task_id)
                results.append(result)

                # Save state after each boost
                state_manager.save_state(project_key, state)

            except (NotImplementedError, subprocess.CalledProcessError, OSError) as e:
                logger.exception(f"Error processing {boost_name} boost")
                ui.update_task(progress, task_id, f"[red]✗ {boost_name} failed[/red]")
                results.append({"boost": boost_name, "status": "failed", "message": str(e)})

    return results


def _print_summary(results: list[dict[str, str]], ui: RichUI) -> None:
    """Print summary table of boost execution results."""
    ui.print_summary(results)


@app.command()
def run(
    path: str = typer.Option(
        ".",
        "--path",
        "-p",
        help="Path to the repository to pimp",
    ),
    wizard: bool = typer.Option(  # noqa: FBT001
        False,
        "--wizard",
        "-w",
        help="Enable interactive wizard mode (not implemented yet)",
    ),
) -> None:
    """Pimp a repository."""
    ui = RichUI()

    if wizard:
        ui.print_warning("Wizard mode is not yet implemented")
        raise Exit(code=1)

    repo_path = Path(path).resolve()

    # Pre-flight checks
    ui.print_bold(f"Pimping repository at: {repo_path}")
    _validate_path(repo_path, ui)

    # Setup git and state
    git_manager, state, state_manager, project_key = _setup_git_and_state(repo_path, ui)

    # Detect existing configs
    ui.print_cyan("Detecting existing configuration...")
    detect_all(repo_path)
    ui.print_success("Detection complete")

    # Initialize boosts
    boost_classes = get_all_boosts()
    ui.print_cyan(f"Found {len(boost_classes)} boosts")

    # Execute boosts
    results = _execute_boosts(boost_classes, repo_path, state, git_manager, state_manager, project_key, ui)

    # Print summary
    _print_summary(results, ui)


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
