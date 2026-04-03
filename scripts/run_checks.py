"""Trigger and watch the CI Checks workflow."""  # noqa: INP001

import json
import subprocess
import time
from datetime import UTC, datetime
from typing import Any

import typer
from rich.console import Console
from rich.live import Live
from rich.table import Table

_WORKFLOW = "Checks"
_POLL_INTERVAL = 3
_TRIGGER_TIMEOUT = 30
_SECONDS_PER_MINUTE = 60

console = Console(
    width=120,
)


def main(watch: str | None = typer.Option(None, help="Watch an existing run ID without triggering.")) -> None:
    branch = _current_branch()
    run_id = watch or _trigger_and_detect(branch=branch)
    _watch_run(run_id=run_id)


def _current_branch() -> str:
    return subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], text=True).strip()  # noqa: S607


def _latest_run_id(branch: str) -> str:
    result = subprocess.run(  # noqa: S603
        ["gh", "run", "list", "--workflow", _WORKFLOW, "--branch", branch, "--limit", "1", "--json", "databaseId"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    data = json.loads(result.stdout or "[]")
    return str(data[0]["databaseId"]) if data else ""


def _trigger_and_detect(branch: str) -> str:
    before_id = _latest_run_id(branch=branch)
    console.print(f"Triggering [bold]{_WORKFLOW}[/bold] on [cyan]{branch}[/cyan]...")
    subprocess.run(["gh", "workflow", "run", _WORKFLOW, "--ref", branch], check=True)  # noqa: S603, S607

    deadline = time.monotonic() + _TRIGGER_TIMEOUT
    while time.monotonic() < deadline:
        time.sleep(_POLL_INTERVAL)
        new_id = _latest_run_id(branch=branch)
        if new_id and new_id != before_id:
            console.print(f"Run ID: [bold]{new_id}[/bold]")
            return new_id

    raise typer.Exit(code=1)


def _watch_run(run_id: str) -> None:
    console.print(f"Watching run [bold]{run_id}[/bold] (Ctrl+C to exit)\n")
    try:
        with Live(console=console, refresh_per_second=1) as live:
            while True:
                data = _fetch_run(run_id=run_id)
                live.update(_render(data=data))
                if data.get("conclusion"):
                    break
                time.sleep(_POLL_INTERVAL)
    except KeyboardInterrupt:
        pass


def _fetch_run(run_id: str) -> dict[str, Any]:
    result = subprocess.run(  # noqa: S603
        ["gh", "run", "view", run_id, "--json", "status,conclusion,jobs"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    return json.loads(result.stdout or "{}")  # type: ignore[no-any-return]


def _render(data: dict[str, Any]) -> Table:
    conclusion = data.get("conclusion") or ""
    overall_icon = _conclusion_icon(conclusion) if conclusion else "⏳"

    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
    table.add_column("")
    table.add_column("Job")
    table.add_column("Duration", justify="right")

    for job in data.get("jobs", []):
        icon = _job_icon(job)
        name = job.get("name", "")
        duration = _job_duration(job)
        table.add_row(icon, name, duration)

    table.caption = f"{overall_icon} {conclusion.upper()}" if conclusion else f"{overall_icon} running..."
    return table


def _job_icon(job: dict[str, Any]) -> str:
    status = job.get("status", "")
    conclusion = job.get("conclusion", "") or ""
    if conclusion == "success":
        return "[green]✓[/green]"
    if conclusion in ("failure", "timed_out"):
        return "[red]✗[/red]"
    if conclusion == "cancelled":
        return "[yellow]⊘[/yellow]"
    if conclusion == "skipped":
        return "[dim]-[/dim]"
    if status == "in_progress":
        return "[cyan]●[/cyan]"
    return "[dim]○[/dim]"


def _conclusion_icon(conclusion: str) -> str:
    if conclusion == "success":
        return "[green]✓[/green]"
    if conclusion in ("failure", "timed_out"):
        return "[red]✗[/red]"
    return "[yellow]⊘[/yellow]"


_MIN_VALID_YEAR = 2000


def _job_duration(job: dict[str, Any]) -> str:
    started = job.get("startedAt")
    completed = job.get("completedAt")
    if not started:
        return ""
    start_dt = datetime.fromisoformat(started)
    if start_dt.year < _MIN_VALID_YEAR:
        return ""
    completed_dt = datetime.fromisoformat(completed) if completed else None
    end_dt = completed_dt if completed_dt and completed_dt.year >= _MIN_VALID_YEAR else datetime.now(UTC)
    seconds = int((end_dt - start_dt).total_seconds())
    if seconds < _SECONDS_PER_MINUTE:
        return f"{seconds}s"
    return f"{seconds // _SECONDS_PER_MINUTE}m{seconds % _SECONDS_PER_MINUTE:02d}s"


if __name__ == "__main__":
    typer.run(main)
