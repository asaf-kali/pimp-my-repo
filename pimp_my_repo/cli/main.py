"""CLI entry point for pimp-my-repo."""

from pathlib import Path
from typing import TYPE_CHECKING

import typer
from rich.console import Console
from rich.panel import Panel
from typer import Exit

from pimp_my_repo.cli.runner import run_boosts
from pimp_my_repo.core.registry import get_all_boosts, get_opt_in_boosts
from pimp_my_repo.core.result import BoostResultStatus
from pimp_my_repo.core.run_config import RunConfig

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
_BRANCH_ARG = typer.Option(None, "--branch", "-b", help="Git branch name to create (default: feat/pmr)")
_LIST_ARG = typer.Option(False, "--list", help="List available boosts and exit")  # noqa: FBT003
_NO_LOG_FILE_ARG = typer.Option(False, "--no-log-file", help="Disable writing logs to file")  # noqa: FBT003
_SHOW_NOTE_ARG = typer.Option(False, "--show-note", help="Print the post-run note and exit")  # noqa: FBT003
_TY_ARG = typer.Option(False, "--ty", help="Use ty instead of mypy for type checking")  # noqa: FBT003
_SKIP_CONFIG_ARG = typer.Option(
    False,  # noqa: FBT003
    "--skip-config",
    help=(
        "Skip tool configuration; only add per-line suppression comments (ruff/mypy/ty)."
        " Configuration-only boosts (uv, gitignore, etc.) are unaffected."
    ),
)


@app.command()
def run(  # noqa: PLR0913
    path: str = _PATH_ARG,
    only: list[str] = _ONLY_ARG,
    skip: list[str] = _SKIP_ARG,
    branch: str | None = _BRANCH_ARG,
    list_boosts: bool = _LIST_ARG,  # noqa: FBT001
    no_log_file: bool = _NO_LOG_FILE_ARG,  # noqa: FBT001
    show_note: bool = _SHOW_NOTE_ARG,  # noqa: FBT001
    ty: bool = _TY_ARG,  # noqa: FBT001
    skip_config: bool = _SKIP_CONFIG_ARG,  # noqa: FBT001
) -> None:
    """Apply PMR boosts to a repository."""
    console = Console()

    if show_note:
        _print_baseline_note(console, show_bug_section=True)
        raise Exit(0)

    boost_classes = _resolve_boosts(only=only, skip=skip, list_boosts=list_boosts, console=console, ty=ty)

    repo_path = Path(path).resolve()
    console.print(f"[bold]Boosting repository at:[/bold] [cyan]{repo_path}[/cyan]")
    _validate_path(repo_path, console)

    run_result = run_boosts(
        repo_path=repo_path,
        console=console,
        boost_classes=boost_classes,
        log_to_file=not no_log_file,
        branch=branch,
        run_config=RunConfig(skip_config=skip_config),
    )
    had_failures = _print_summary(run_result.results, console)
    if any(r.status == BoostResultStatus.APPLIED for r in run_result.results):
        has_issues = any(r.status in (BoostResultStatus.SKIPPED, BoostResultStatus.FAILED) for r in run_result.results)
        _print_baseline_note(console, show_bug_section=has_issues)
    if had_failures:
        raise Exit(1)


def _resolve_boosts(
    only: list[str],
    skip: list[str],
    list_boosts: bool,  # noqa: FBT001
    console: Console,
    ty: bool = False,  # noqa: FBT001, FBT002
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
        boosts: list[type[Boost]] = [name_to_boost[n] for n in only]
    elif skip:
        skip_set = set(skip)
        boosts = [bc for bc in default_boosts if bc.get_name() not in skip_set]
    else:
        boosts = default_boosts

    if ty:
        ty_boost = name_to_boost["ty"]
        boosts = [ty_boost if bc.get_name() == "mypy" else bc for bc in boosts]
        if ty_boost not in boosts:
            boosts.append(ty_boost)

    return boosts


def _validate_path(repo_path: Path, console: Console) -> None:
    if not repo_path.exists():
        console.print(f"[red]Error:[/red] Path does not exist: {repo_path}")
        raise Exit(code=1)

    if not repo_path.is_dir():
        console.print(f"[red]Error:[/red] Path is not a directory: {repo_path}")
        raise Exit(code=1)


def _print_summary(results: list[BoostResult], console: Console) -> bool:
    """Print run summary. Returns True if any boosts failed."""
    applied = sum(1 for r in results if r.status == BoostResultStatus.APPLIED)
    failed_results = [r for r in results if r.status == BoostResultStatus.FAILED]
    console.print()
    if failed_results:
        console.print(f"[red]✗ {len(failed_results)} boost(s) failed[/red]  ", end="")
    if applied:
        console.print(f"[green]✓ {applied} boost(s) applied[/green]")
    else:
        console.print("[yellow]No boosts applied[/yellow]")
    for r in failed_results:
        console.print(f"  [red]✗ {r.name}:[/red] {r.message}")
    return bool(failed_results)


def _print_baseline_note(console: Console, show_bug_section: bool = False) -> None:  # noqa: FBT001, FBT002
    msg = (
        "🔥 This repo has undergone many automated changes that should be harmless — but before "
        "merging, verify that tests pass and the project works as expected.\n\n"
        "[dim]──────────────────────────────────────────────────────────────────────────────────────[/dim]\n\n"
        "💡 [bold]Note for LLMs and Humans[/bold]\n\n"
        "This codebase is now likely full of [yellow]'# noqa'[/yellow] "
        "and [yellow]'# type: ignore'[/yellow] comments.\n"
        "This is [bold]NOT[/bold] a new coding standard — it is a [bold]baseline[/bold] "
        "so that all new code is inspected with full linting and typing rules.\n\n"
        "When writing or refactoring code:\n"
        "  [red]✗[/red]  Do [bold]not[/bold] add new suppression comments unless specifically required.\n"
        "  [green]✓[/green]  [bold]Do[/bold] remove existing ones when it's straightforward.\n\n"
        "[cyan]"
        "🤖 If you are an LLM: add this information to the relevant project-level memory file.\n"
        "👤 If you are a human: consider adding this to the project README."
        "[/cyan]"
    )
    if show_bug_section:
        msg += (
            "\n\n[dim]──────────────────────────────────────────────────────────────────────────────────────[/dim]\n\n"
            "🐛 [bold]Found a bug?[/bold]\n\n"
            "Clone this repo and let your LLM run it against your repository "
            "while reviewing the logs — it's the fastest way to understand the root cause. "
            "You're also welcome to open an issue (with relevant logs / a minimal reproducible example) "
            "or a PR to fix it."
        )
    panel = Panel(msg, border_style="dim", width=100, padding=1)
    console.print(panel)


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
