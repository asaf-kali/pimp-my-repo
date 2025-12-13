"""Detection of existing project configuration files."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def detect_dependency_files(repo_path: Path) -> dict[str, bool]:
    """Detect existing dependency management files.

    Args:
        repo_path: Path to the repository root

    Returns:
        Dictionary mapping file names to their existence status

    """
    dependency_files = {
        "requirements.txt": False,
        "setup.py": False,
        "pyproject.toml": False,
        "Pipfile": False,
        "poetry.lock": False,
        "Pipfile.lock": False,
    }

    for file_name in dependency_files:
        file_path = repo_path / file_name
        dependency_files[file_name] = file_path.exists()

    return dependency_files


def detect_existing_configs(repo_path: Path) -> dict[str, bool]:
    """Detect existing configuration files for tools.

    Args:
        repo_path: Path to the repository root

    Returns:
        Dictionary mapping config file names to their existence status

    """
    config_files = {
        ".ruff.toml": False,
        "ruff.toml": False,
        "mypy.ini": False,
        ".mypy.ini": False,
        ".pre-commit-config.yaml": False,
        "pre-commit-config.yaml": False,
        "justfile": False,
        "Makefile": False,
        "makefile": False,
    }

    for file_name in config_files:
        file_path = repo_path / file_name
        config_files[file_name] = file_path.exists()

    return config_files


def detect_all(repo_path: Path) -> dict[str, dict[str, bool]]:
    """Detect all existing files (dependencies and configs).

    Args:
        repo_path: Path to the repository root

    Returns:
        Dictionary with 'dependencies' and 'configs' keys

    """
    return {
        "dependencies": detect_dependency_files(repo_path),
        "configs": detect_existing_configs(repo_path),
    }
