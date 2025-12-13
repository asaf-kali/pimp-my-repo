"""State management for pimp-my-repo."""

from pathlib import Path

from pimp_my_repo.models.state import State


def _path_safe_project_key(project_key: str) -> str:
    """Make a project key path safe."""
    return project_key.replace("/", "_")


class StateManager:
    """Manages state persistence for pimp-my-repo."""

    def __init__(self, state_dir: Path | None = None) -> None:
        """Initialize StateManager with state directory."""
        self._state_dir = state_dir or Path.home() / ".local" / "share" / "pimp-my-repo"

    def get_state_path(self, project_key: str) -> Path:
        """Get the state file path for a project."""
        path_safe_project_key = _path_safe_project_key(project_key)
        self._state_dir.mkdir(parents=True, exist_ok=True)
        return self._state_dir / f"{path_safe_project_key}.json"

    def load_state(self, project_key: str) -> State | None:
        """Load state for a project."""
        state_path = self.get_state_path(project_key)
        if not state_path.exists():
            return None
        with state_path.open("r") as f:
            return State.model_validate_json(f.read())

    def save_state(self, project_key: str, state: State) -> None:
        """Save state for a project."""
        state_path = self.get_state_path(project_key)
        with state_path.open("w") as f:
            f.write(state.model_dump_json())
