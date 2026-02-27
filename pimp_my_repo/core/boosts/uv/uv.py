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
from pimp_my_repo.core.tools.subprocess import run_command
from pimp_my_repo.core.tools.uv import UvNotFoundError

if TYPE_CHECKING:
    from pathlib import Path

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

    def _uv_is_available(self) -> bool:
        if self._check_uv_installed():
            return True
        if not self._install_uv():
            return False
        return self._check_uv_installed()

    def _check_uv_installed(self) -> bool:
        """Check if UV is installed."""
        try:
            result = self.uv.run("--version", check=False)
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
        uv_section["package"] = True
        return pyproject_data

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
        """Detect and categorize all requirements files.

        Returns:
            ProjectRequirements with main file and grouped files

        """
        result = ProjectRequirements()

        # Find all requirements files
        suffix_files = list(self.tools.repo_path.rglob("requirements*.txt"))
        prefix_files = list(self.tools.repo_path.rglob("*-requirements.txt"))
        all_files = set(suffix_files) | set(prefix_files)

        for file_path in all_files:
            self._categorize_requirements_file(file_path, result)

        return result

    def _is_setup_cfg_bare(self) -> bool:
        """Return True if setup.cfg is absent or has no [metadata]/[options] sections."""
        setup_cfg_path = self.tools.repo_path / "setup.cfg"
        if not setup_cfg_path.exists():
            return True
        config = configparser.ConfigParser()
        config.read(setup_cfg_path)
        return not any(s in config.sections() for s in ("metadata", "options"))

    def _parse_setup_py_str_kwargs(self) -> dict[str, str]:
        """AST-walk setup.py and return only string-literal kwargs from setup()."""
        setup_py_path = self.tools.repo_path / "setup.py"
        if not setup_py_path.exists():
            return {}
        try:
            source = setup_py_path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except SyntaxError, OSError:
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

    def _has_migration_source(self) -> bool:
        """Check if there are any migration sources supported by migrate-to-uv.

        migrate-to-uv supports: Poetry (pyproject.toml with [tool.poetry]),
        Pipfile, and setup.cfg with [metadata]/[options]. A bare setup.cfg (no
        metadata) or a bare setup.py triggers best-effort augmentation instead.
        """
        detected = detect_dependency_files(self.tools.repo_path)

        if detected.poetry_lock:
            return True
        if detected.pipfile or detected.pipfile_lock:
            return True
        if self._has_poetry_config():
            return True
        if detected.setup_cfg and not self._is_setup_cfg_bare():
            return True
        # Best-effort: treat setup.py as a migration source when no pyproject.toml yet
        if detected.setup_py and not detected.pyproject_toml:
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

        # Best-effort: augment bare/missing setup.cfg from setup.py before migrating
        detected = detect_dependency_files(self.tools.repo_path)
        if detected.setup_py and self._is_setup_cfg_bare():
            logger.info("Bare/missing setup.cfg with setup.py detected; attempting best-effort augmentation...")
            self._augment_setup_cfg_from_setup_py()

        # Run migrate-to-uv for main migration (handles setup.py, Pipfile, Poetry, etc.)
        logger.info("Detected migration source, using uvx migrate-to-uv...")
        self.uv.run_uvx("migrate-to-uv")
        logger.info("Migration completed successfully")

        # Add grouped requirements files after migration
        for group, files in requirements_files.groups.items():
            for file_path in files:
                self.uv.add_from_requirements_file(file_path, group=group)

    def _ensure_pyproject_exists(self) -> None:
        pyproject_path = self.tools.repo_path / "pyproject.toml"
        if pyproject_path.exists():
            return
        logger.info("No pyproject.toml found, creating minimal one...")
        pyproject_data = document()
        project_name = self.tools.repo_path.name.lower().replace(" ", "-").replace("_", "-").strip("-")
        project_table = table()
        project_table["name"] = project_name
        project_table["version"] = "0.1.0"
        project_table["requires-python"] = ">=3.8"
        pyproject_data["project"] = project_table
        self.pyproject.write(pyproject_data)

    def _ensure_uv_config_present(self) -> None:
        pyproject_data = self.pyproject.read()
        pyproject_data = self._ensure_uv_config(pyproject_data)
        self.pyproject.write(pyproject_data)

    def _generate_uv_lock(self) -> None:
        logger.info("Generating uv.lock...")
        self.uv.run("lock")
        logger.info("Successfully generated uv.lock")

    def apply(self) -> None:
        """Create pyproject.toml if needed and migrate using uvx migrate-to-uv."""
        if not self._uv_is_available():
            msg = "uv is not installed and could not be installed automatically"
            raise UvNotFoundError(msg)
        self._run_migration_if_needed()
        self._ensure_pyproject_exists()
        self._ensure_uv_config_present()
        self._generate_uv_lock()

    def commit_message(self) -> str:
        """Generate commit message for UV boost."""
        return "✨ Add UV dependency management"
