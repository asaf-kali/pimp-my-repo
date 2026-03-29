"""UV boost implementation."""

import ast
import configparser
import re
import subprocess
import sys
from typing import TYPE_CHECKING, Any

from loguru import logger
from tomlkit import TOMLDocument, document, table

from pimp_my_repo.core.boosts.base import Boost
from pimp_my_repo.core.boosts.uv.detector import detect_dependency_files
from pimp_my_repo.core.boosts.uv.models import ProjectRequirements
from pimp_my_repo.core.boosts.uv.python_version import resolve_requires_python
from pimp_my_repo.core.tools.subprocess import run_command
from pimp_my_repo.core.tools.uv import UvNotFoundError

if TYPE_CHECKING:
    from pathlib import Path

_MAX_PYTHON_MINOR: int = 14  # Upper bound for requires-python search; update as new Python releases land
_MIN_PYTHON_MINOR: int = 8

_SETUP_PY_TO_SETUP_CFG: dict[str, str] = {
    "name": "name",
    "version": "version",
    "description": "description",
    "author": "author",
    "author_email": "author-email",
    "url": "url",
    "license": "license",
    "keywords": "keywords",
}


class UvBoost(Boost):
    """Boost for integrating UV dependency management."""

    def apply(self) -> None:
        """Create pyproject.toml if needed and migrate using uvx migrate-to-uv."""
        if not self._uv_is_available():
            msg = "uv is not installed and could not be installed automatically"
            raise UvNotFoundError(msg)
        self._run_migration_if_needed()
        self._ensure_pyproject_exists()
        self._ensure_uv_config_present()
        self._lock_with_requires_python()
        logger.info("Running final uv sync --all-groups...")
        self.uv.exec("sync", "--all-groups")
        logger.info("Venv fully synced")

    def commit_message(self) -> str:
        """Generate commit message for UV boost."""
        return "✨ Add UV dependency management"

    def _uv_is_available(self) -> bool:
        if self._check_uv_installed():
            return True
        if not self._install_uv():
            return False
        return self._check_uv_installed()

    def _check_uv_installed(self) -> bool:
        """Check if UV is installed."""
        try:
            result = self.uv.exec("--version", check=False)
        except subprocess.CalledProcessError:
            return False
        except OSError:
            return False
        return result.returncode == 0

    def _install_uv(self) -> bool:
        """Attempt to install UV automatically."""
        logger.info("UV not found, attempting to install...")
        if self._try_script_install():
            return True
        if self._try_pip_install():
            return True
        logger.error("Failed to install UV automatically")
        return False

    def _try_pip_install(self) -> bool:
        try:
            result = run_command(
                [sys.executable, "-m", "pip", "install", "uv"],
                cwd=self.tools.repo_path,
                check=False,
            )
        except OSError as e:
            logger.debug(f"Failed to install UV via pip: {e}")
            return False
        if result.returncode != 0:
            return False
        logger.info("Successfully installed UV via pip")
        return True

    def _try_script_install(self) -> bool:
        installer_url = "https://astral.sh/uv/install.sh"
        try:
            result = run_command(
                ["sh", "-c", f"curl -LsSf {installer_url} | sh"],
                cwd=self.tools.repo_path,
                check=False,
            )
        except OSError as e:
            logger.debug(f"Failed to install UV via official installer: {e}")
            return False
        if result.returncode != 0:
            return False
        logger.info("Successfully installed UV via official installer")
        return True

    def _ensure_uv_config(self, pyproject_data: TOMLDocument) -> TOMLDocument:
        """Ensure [tool.uv] section exists."""
        if "tool" not in pyproject_data:
            pyproject_data["tool"] = table()
        tool_section: Any = pyproject_data["tool"]
        if "uv" not in tool_section:
            tool_section["uv"] = table()
        uv_section: Any = tool_section["uv"]
        # Don't set package=true when setup.py exists: uv would try to build the project
        # via setuptools, which conflicts with a minimal pyproject.toml we may have created.
        # After migrate-to-uv runs, setup.py is removed, so this branch applies only to
        # projects that bypass migration (e.g. setup.py-only without migration source).
        if not (self.tools.repo_path / "setup.py").exists():
            uv_section["package"] = self._is_installable_package()
        return pyproject_data

    def _is_installable_package(self) -> bool:
        """Return True if the project has a real Python package structure.

        A project is a package if it has a ``src/`` directory or at least one
        top-level directory containing an ``__init__.py``.  Plain script repos
        and data-science projects typically have neither, so we mark them as
        ``package = false`` to prevent uv from trying to build them.
        """
        repo = self.tools.repo_path
        if (repo / "src").is_dir():
            return True
        return any((d / "__init__.py").exists() for d in repo.iterdir() if d.is_dir() and not d.name.startswith("."))

    def _extract_group_from_filename(self, filename: str) -> str | None:
        """Extract group name from requirements filename.

        Returns:
            Group name if found, None for main requirements.txt

        """
        # requirements.txt -> None (main)
        if filename == "requirements.txt":
            return None

        # requirements-X.txt -> X
        match = re.match(r"^requirements-([^.]+)\.txt$", filename)
        if match:
            return match.group(1)

        # requirements.X.txt -> X
        match = re.match(r"^requirements\.([^.]+)\.txt$", filename)
        if match:
            return match.group(1)

        # X-requirements.txt -> X
        match = re.match(r"^([^-]+)-requirements\.txt$", filename)
        if match:
            return match.group(1)

        return None

    def _categorize_requirements_file(self, file_path: Path, result: ProjectRequirements) -> None:
        """Categorize a single requirements file into main or grouped.

        Args:
            file_path: Path to the requirements file
            result: ProjectRequirements object to update

        """
        # Get relative path from repo root for consistent handling
        try:
            rel_path = file_path.relative_to(self.tools.repo_path)
        except ValueError:
            return

        filename = rel_path.name
        group = self._extract_group_from_filename(filename)

        if group is None:
            # Main requirements.txt
            if filename == "requirements.txt":
                result.main = file_path
        else:
            # Grouped requirements file
            if group not in result.groups:
                result.groups[group] = []
            result.groups[group].append(file_path)

    def _detect_requirements_files(self) -> ProjectRequirements:
        """Detect and categorize requirements files at the repository root.

        Only scans the root directory (and one level deep for a dedicated
        ``requirements/`` sub-directory) to avoid picking up unrelated files
        such as ``docs/requirements.txt`` or test-fixture templates.

        Returns:
            ProjectRequirements with main file and grouped files

        """
        result = ProjectRequirements()

        root = self.tools.repo_path
        candidates = list(root.glob("requirements*.txt")) + list(root.glob("*-requirements.txt"))

        # Also look inside a top-level ``requirements/`` directory (common convention).
        req_dir = root / "requirements"
        if req_dir.is_dir():
            candidates += list(req_dir.glob("*.txt"))

        for file_path in candidates:
            self._categorize_requirements_file(file_path, result)

        return result

    def _is_setup_cfg_bare(self) -> bool:
        """Return True if setup.cfg is absent or has no [options] section.

        migrate-to-uv requires [options] (for install_requires etc.) to recognise setup.cfg
        as a migration source. A setup.cfg with only [metadata] and no [options] is treated
        as bare so that the best-effort augmentation path is used instead.
        """
        setup_cfg_path = self.tools.repo_path / "setup.cfg"
        if not setup_cfg_path.exists():
            return True
        config = configparser.ConfigParser()
        config.read(setup_cfg_path)
        return "options" not in config.sections()

    def _parse_setup_py_str_kwargs(self) -> dict[str, str]:
        """AST-walk setup.py and return only string-literal kwargs from setup()."""
        setup_py_path = self.tools.repo_path / "setup.py"
        if not setup_py_path.exists():
            return {}
        try:
            source = setup_py_path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (SyntaxError, OSError):  # fmt: skip
            return {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            is_setup = (isinstance(func, ast.Name) and func.id == "setup") or (
                isinstance(func, ast.Attribute) and func.attr == "setup"
            )
            if not is_setup:
                continue
            result: dict[str, str] = {}
            for kw in node.keywords:
                if kw.arg and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                    result[kw.arg] = kw.value.value
            return result
        return {}

    def _augment_setup_cfg_from_setup_py(self) -> None:
        """Write a [metadata] section into setup.cfg from setup.py string kwargs."""
        kwargs = self._parse_setup_py_str_kwargs()
        if not kwargs:
            logger.debug("No extractable string metadata in setup.py; skipping setup.cfg augmentation")
            return
        setup_cfg_path = self.tools.repo_path / "setup.cfg"
        config = configparser.ConfigParser()
        if setup_cfg_path.exists():
            config.read(setup_cfg_path)
        if "metadata" not in config:
            config["metadata"] = {}
        for setup_key, cfg_key in _SETUP_PY_TO_SETUP_CFG.items():
            if setup_key in kwargs and cfg_key not in config["metadata"]:
                config["metadata"][cfg_key] = kwargs[setup_key]
        with setup_cfg_path.open("w", encoding="utf-8") as f:
            config.write(f)
        logger.info("Augmented setup.cfg with metadata from setup.py (best-effort)")

    def _has_project_table(self) -> bool:
        """Return True if pyproject.toml already has a [project] section (PEP 621)."""
        try:
            data = self.pyproject.read()
        except (OSError, ValueError):  # fmt: skip
            return False
        return "project" in data

    def _has_migration_source(self) -> bool:
        """Check if there are any migration sources supported by migrate-to-uv.

        migrate-to-uv supports: Poetry (pyproject.toml with [tool.poetry]),
        Pipfile, and setup.cfg with [metadata]/[options]. A bare setup.cfg (no
        metadata) or a bare setup.py triggers best-effort augmentation instead.

        Projects that already have a [project] table (PEP 621) need no migration.
        """
        detected = detect_dependency_files(self.tools.repo_path)

        # Already using modern PEP 621 format — migrate-to-uv has nothing to do.
        if detected.pyproject_toml and self._has_project_table():
            return False

        if detected.poetry_lock:
            return True
        if detected.pipfile or detected.pipfile_lock:
            return True
        if self._has_poetry_config():
            return True
        if detected.setup_cfg and not self._is_setup_cfg_bare():
            return True

        requirements_files = self._detect_requirements_files()
        return requirements_files.main is not None or bool(requirements_files.groups)

    def _has_poetry_config(self) -> bool:
        pyproject_path = self.tools.repo_path / "pyproject.toml"
        if not pyproject_path.exists():
            return False
        try:
            pyproject_data = self.pyproject.read()
        except (OSError, ValueError):  # fmt: skip
            return False
        tool_section: Any = pyproject_data.get("tool", {})
        return isinstance(tool_section, dict) and bool(tool_section.get("poetry"))

    def _run_migration_if_needed(self) -> None:
        """Run migration and add grouped requirements files."""
        if not self._has_migration_source():
            return

        # Detect and categorize requirements files
        requirements_files = self._detect_requirements_files()

        # Run migrate-to-uv for main migration (handles Pipfile, Poetry, setup.cfg with [options], etc.)
        logger.info("Detected migration source, using uvx migrate-to-uv...")
        # --skip-lock: let _lock_with_requires_python() handle locking with proper version detection.
        # Without this, migrate-to-uv runs `uv lock` internally using the current Python (e.g. 3.14),
        # which fails for old packages that have no pre-built wheel and can't be built with modern setuptools.
        self.uv.exec_uvx("migrate-to-uv", "--skip-lock")
        logger.info("Migration completed successfully")

        # Add grouped requirements files after migration.
        # migrate-to-uv may already handle some (e.g. requirements-dev.txt → [dependency-groups])
        # and delete those files, so only add files that still exist.
        for group, files in requirements_files.groups.items():
            for file_path in files:
                if file_path.exists():
                    self.uv.add_from_requirements_file(file_path, group=group)

    def _ensure_pyproject_exists(self) -> None:
        pyproject_path = self.tools.repo_path / "pyproject.toml"
        if not pyproject_path.exists():
            logger.info("No pyproject.toml found, creating minimal one...")
            pyproject_data = document()
            project_name = self._infer_project_name()
            project_table = table()
            project_table["name"] = project_name
            project_table["version"] = "0.1.0"
            pyproject_data["project"] = project_table
            self.pyproject.write(pyproject_data)
            return
        self._fix_empty_project_name()

    def _infer_project_name(self) -> str:
        return self.tools.repo_path.name.lower().replace(" ", "-").replace("_", "-").strip("-")

    def _fix_empty_project_name(self) -> None:
        """Fix empty project name left by migrate-to-uv (name must be a valid PEP 508 identifier)."""
        pyproject_data = self.pyproject.read()
        project_section: Any = pyproject_data.get("project")
        if not isinstance(project_section, dict):
            return
        if project_section.get("name"):
            return
        project_name = self._infer_project_name()
        logger.info(f"Fixing empty project name, setting to '{project_name}'...")
        project_section["name"] = project_name
        self.pyproject.write(pyproject_data)

    def _write_requires_python(self, requires_python: str) -> None:
        pyproject_data = self.pyproject.read()
        project_section: Any = pyproject_data.get("project")
        if not isinstance(project_section, dict):
            project_section = table()
            pyproject_data["project"] = project_section
        project_section["requires-python"] = requires_python
        self.pyproject.write(pyproject_data)

    def _remove_requires_python(self) -> None:
        pyproject_data = self.pyproject.read()
        project_section: Any = pyproject_data.get("project")
        if not isinstance(project_section, dict):
            return
        project_section.pop("requires-python", None)
        self.pyproject.write(pyproject_data)

    def _try_lock_and_sync(self) -> bool:
        try:
            self._lock_and_sync()
        except subprocess.CalledProcessError:
            return False
        else:
            return True

    def _ensure_upper_bound(self) -> None:
        """If requires-python is a bare '>=x.y', add the upper bound '<x.(y+1)'."""
        pyproject_data = self.pyproject.read()
        project_section: Any = pyproject_data.get("project")
        if not isinstance(project_section, dict):
            return
        current: str = project_section.get("requires-python", "")
        match = re.fullmatch(r">=(\d+)\.(\d+)", current.strip())
        if not match:
            return
        major, minor = int(match.group(1)), int(match.group(2))
        pinned = f">={major}.{minor},<{major}.{minor + 1}"
        logger.info(f"Adding upper bound to requires-python: '{current}' → '{pinned}'")
        self._write_requires_python(pinned)

    def _lock_with_requires_python(self) -> None:
        """Set requires-python, run uv lock + uv sync --all-groups, searching for a compatible minor."""
        pyproject_data = self.pyproject.read()
        project_section: Any = pyproject_data.get("project")
        if isinstance(project_section, dict) and project_section.get("requires-python"):
            self._ensure_upper_bound()
            self._lock_and_sync()
            return

        initial = resolve_requires_python(repo_path=self.tools.repo_path)
        if initial is None:
            logger.debug("No Python version detected, locking without requires-python")
            self._lock_and_sync()
            return

        match = re.match(r">=3\.(\d+)", initial)
        if not match:
            self._write_requires_python(initial)
            self._lock_and_sync()
            return

        detected_minor = int(match.group(1))
        requires_python = f">=3.{detected_minor},<3.{detected_minor + 1}"
        logger.info(f"Setting requires-python = '{requires_python}'")
        self._write_requires_python(requires_python)
        if self._try_lock_and_sync():
            return

        logger.info(f"Lock+sync failed for '{requires_python}', searching from 3.{_MAX_PYTHON_MINOR} down...")
        for minor in range(_MAX_PYTHON_MINOR, _MIN_PYTHON_MINOR - 1, -1):
            if minor == detected_minor:
                continue
            requires_python = f">=3.{minor},<3.{minor + 1}"
            logger.info(f"Trying requires-python = '{requires_python}'")
            self._write_requires_python(requires_python)
            if self._try_lock_and_sync():
                return

        logger.warning("No compatible requires-python found, removing constraint and locking")
        self._remove_requires_python()
        self._lock_and_sync()

    def _ensure_uv_config_present(self) -> None:
        pyproject_data = self.pyproject.read()
        pyproject_data = self._ensure_uv_config(pyproject_data)
        self.pyproject.write(pyproject_data)

    def _lock_and_sync(self) -> None:
        logger.debug("Running uv lock...")
        self.uv.exec("lock")
        logger.debug("Running uv sync --all-groups...")
        self.uv.exec("sync", "--all-groups")
        logger.debug("uv lock and sync completed successfully")
