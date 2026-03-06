"""Live two-panel dashboard: boost status (left) and log stream (right)."""

from collections import deque
from typing import TYPE_CHECKING

from rich.layout import Layout
from rich.panel import Panel
from rich.text import Text

if TYPE_CHECKING:
    from rich.console import Console, ConsoleOptions, RenderResult

    from pimp_my_repo.core.result import BoostResult

_STATUS_CONFIG: dict[str, tuple[str, str]] = {
    "applied": ("✓", "green"),
    "skipped": ("⊘", "yellow"),
    "failed": ("✗", "red"),
}

_PENDING: tuple[str, str] = ("·", "dim")
_RUNNING: tuple[str, str] = ("▶", "yellow")


class LiveDashboard:
    def __init__(self, boost_names: list[str]) -> None:
        self._boost_names = boost_names
        self._statuses: dict[str, tuple[str, str]] = dict.fromkeys(boost_names, _PENDING)
        self._logs: deque[str] = deque(maxlen=500)
        self.layout = Layout()
        self.layout.split_row(
            Layout(name="left", minimum_size=25),
            Layout(name="right", size=150),
        )
        self._refresh()

    def set_running(self, name: str) -> None:
        self._statuses[name] = _RUNNING
        self._refresh()

    def set_result(self, result: BoostResult) -> None:
        self._statuses[result.name] = _STATUS_CONFIG.get(result.status, ("?", "white"))
        self._refresh()

    def add_log(self, message: object) -> None:
        for line in str(message).rstrip().splitlines():
            self._logs.append(line)
        self._refresh()

    def _refresh(self) -> None:
        self.layout["left"].update(self._make_left())

    def _make_left(self) -> Panel:
        text = Text()
        for name in self._boost_names:
            icon, style = self._statuses[name]
            text.append(f"  {icon} ", style=style)
            text.append(name + "\n", style="cyan")
        return Panel(text, title="Boosts", border_style="blue")

    def _make_right(self, max_lines: int) -> Panel:
        # Show only the last max_lines lines so newest logs are always visible
        lines = list(self._logs)[-max_lines:]
        text = Text(no_wrap=True)
        for line in lines:
            text.append_text(Text.from_ansi(line))
            text.append("\n")
        return Panel(text, title="Logs", border_style="dim")

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:  # noqa: D105
        height = max(4, int(console.height * 0.80))
        self.layout["right"].update(self._make_right(max_lines=height - 2))
        yield from self.layout.__rich_console__(console, options.update(height=height))
