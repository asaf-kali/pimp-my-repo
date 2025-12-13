"""Rich-based UI implementation for pimp-my-repo."""

from typing import TYPE_CHECKING

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TaskID, TextColumn
from rich.table import Table

if TYPE_CHECKING:
    from contextlib import AbstractContextManager


class RichUI:
    """Rich-based UI implementation."""

    def __init__(self) -> None:
        """Initialize Rich UI."""
        self.console = Console()

    def print_info(self, message: str) -> None:
        """Print an info message."""
        self.console.print(message)

    def print_success(self, message: str) -> None:
        """Print a success message."""
        self.console.print(f"[green]✓[/green] {message}")

    def print_error(self, message: str) -> None:
        """Print an error message."""
        self.console.print(f"[red]Error:[/red] {message}")

    def print_warning(self, message: str) -> None:
        """Print a warning message."""
        self.console.print(f"[yellow]{message}[/yellow]")

    def print_cyan(self, message: str) -> None:
        """Print a cyan-colored message."""
        self.console.print(f"[cyan]{message}[/cyan]")

    def print_bold(self, message: str) -> None:
        """Print a bold message."""
        self.console.print(f"[bold]{message}[/bold]")

    def create_progress_context(self) -> AbstractContextManager[Progress]:
        """Create a progress context manager."""
        return Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console,
        )

    def create_task(self, progress: Progress, description: str) -> TaskID:
        """Create a new task in the progress tracker."""
        return progress.add_task(description, total=None)

    def update_task(self, progress: Progress, task_id: TaskID, description: str) -> None:
        """Update a task's description."""
        progress.update(task_id, description=description)

    def print_summary(self, results: list[dict[str, str]]) -> None:
        """Print summary table of boost execution results."""
        self.console.print("\n[bold]Summary:[/bold]")
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

        self.console.print(table)

        # Final message
        applied_count = sum(1 for r in results if r["status"] == "applied")
        if applied_count > 0:
            self.console.print(f"\n[green]✓ Successfully applied {applied_count} boost(s)[/green]")
        else:
            self.console.print("\n[yellow]No boosts were applied[/yellow]")
