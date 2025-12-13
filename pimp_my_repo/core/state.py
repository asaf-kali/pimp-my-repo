"""State management for pimp-my-repo."""

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pimp_my_repo.models.state import State


class StateManager:
    """Manages state persistence for pimp-my-repo."""

    def __init__(self, state_dir: Path | None = None) -> None:
        """Initialize StateManager with state directory."""
        if state_dir is None:
            state_dir = Path.home() / ".local" / "share" / "pimp-my-repo"
        self.state_dir = state_dir

    def get_state_path(self, project_key: str) -> Path:
        """Get the state file path for a project."""
        self.state_dir.mkdir(parents=True, exist_ok=True)
        return self.state_dir / f"{project_key}.json"

    def load_state(self, project_key: str) -> State | None:
        """Load state for a project."""
        raise NotImplementedError

    def save_state(self, project_key: str, state: State) -> None:
        """Save state for a project."""
        raise NotImplementedError
