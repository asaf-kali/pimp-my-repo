"""Repository feature detection helpers shared across boosts."""

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

_RECIPE_NAME_PATTERN = re.compile(r"^([a-zA-Z0-9][a-zA-Z0-9_-]*)")
_TEST_DIR_NAMES = ("tests", "test")
_TEST_FILE_GLOB = "test_*.py"


def has_tool_section(*, repo_path: Path, tool: str) -> bool:
    """Return True if ``[tool.<tool>`` appears in the repo's pyproject.toml."""
    pyproject = repo_path / "pyproject.toml"
    if not pyproject.exists():
        return False
    content = pyproject.read_text(encoding="utf-8")
    return f"[tool.{tool}" in content


def get_justfile_recipes(*, justfile_path: Path) -> set[str]:
    """Parse a justfile and return the set of defined recipe names."""
    content = justfile_path.read_text(encoding="utf-8")
    recipes: set[str] = set()
    for line in content.splitlines():
        m = _RECIPE_NAME_PATTERN.match(line)
        if m and ":=" not in line and ":" in line:
            recipes.add(m.group(1))
    return recipes


def has_tests(*, repo_path: Path) -> bool:
    """Return True if the repo has a tests directory or any ``test_*.py`` file outside hidden dirs."""
    if any((repo_path / name).is_dir() for name in _TEST_DIR_NAMES):
        return True
    for path in repo_path.rglob(_TEST_FILE_GLOB):
        relative = path.relative_to(repo_path)
        if not any(part.startswith(".") for part in relative.parts):
            return True
    return False
