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
# Indentation prepended to continuation lines when a log message is wrapped.
_LOG_INDENT = "         "


class LiveDashboard:
    def __init__(self, boost_names: list[str]) -> None:
        self._boost_names = boost_names
        self._statuses: dict[str, tuple[str, str]] = dict.fromkeys(boost_names, _PENDING)
        self._logs: deque[str] = deque(maxlen=500)
        self.layout = Layout()
        self.layout.split_row(
            Layout(name="left", size=25),
            Layout(name="right"),
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

    def _make_right(self, *, max_lines: int) -> Panel:
        return Panel(_LogContent(self._logs, max_lines), title="Logs", border_style="dim")

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:  # noqa: D105
        height = max(4, int(console.height * 0.80))
        self.layout["right"].update(self._make_right(max_lines=height - 2))
        yield from self.layout.__rich_console__(console, options.update(height=height))


class _LogContent:
    """Renderable that wraps log lines to the width Rich provides at render time.

    Because this object implements ``__rich_console__``, Rich calls it with
    ``options.max_width`` already set to the Panel content width.
    """

    def __init__(self, logs: deque[str], max_lines: int) -> None:
        self._logs = logs
        self._max_lines = max_lines

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        width = options.max_width
        visual_lines = [chunk for raw_line in self._logs for chunk in _wrap_log_line(raw_line, width)]
        text = Text(no_wrap=True)
        for chunk in visual_lines[-self._max_lines :]:
            text.append_text(chunk)
            text.append("\n")
        yield from console.render(text, options)


def _wrap_log_line(line: str, width: int) -> list[Text]:
    """Split one log line into width-bounded Text chunks.

    The first chunk uses the full width; each continuation chunk is indented
    by ``_LOG_INDENT`` so it is visually tied to the line above.
    """
    text = Text.from_ansi(line)
    plain_len = len(text.plain)
    indent_len = len(_LOG_INDENT)
    cont_width = width - indent_len

    if plain_len <= width or cont_width <= 0:
        return [text]

    chunks: list[Text] = [text[:width]]
    pos = width
    while pos < plain_len:
        chunk = Text(_LOG_INDENT)
        chunk.append_text(text[pos : pos + cont_width])
        chunks.append(chunk)
        pos += cont_width
    return chunks
