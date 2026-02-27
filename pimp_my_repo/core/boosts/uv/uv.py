"""UV boost implementation."""

import subprocess
import sys
from typing import Any

from loguru import logger
from tomlkit import TOMLDocument, document, table

from pimp_my_repo.core.boosts.base import Boost, BoostSkippedError
from pimp_my_repo.core.boosts.uv.detector import detect_dependency_files


class UvBoost(Boost):
    """Boost for integrating UV dependency management."""

    _uv_version_failed: bool = False

    def _uv_is_available(self) -> bool:
        if self._check_uv_installed():
            return True
        # uv binary exists but returned non-zero — treat as available (version mismatch, etc.)
        if self._uv_version_failed:
            return True
        if not self._install_uv():
            return False
        return self._check_uv_installed()

    def _check_uv_installed(self) -> bool:
        """Check if UV is installed."""
        self._uv_version_failed = False
        try:
            result = self.uv.run("--version", check=False)
        except subprocess.CalledProcessError:
            self._uv_version_failed = True
            return False
        except OSError:
            return False
        return result.returncode == 0

    def _install_uv(self) -> bool:
        """Attempt to install UV automatically."""
        logger.info("UV not found, attempting to install...")
        if self._try_pip_install():
            return True
        if self._try_script_install():
            return True
        logger.error("Failed to install UV automatically")
        return False

    def _try_pip_install(self) -> bool:
        try:
            result = subprocess.run(  # noqa: S603
                [sys.executable, "-m", "pip", "install", "uv"],
                capture_output=True,
                text=True,
                check=False,
            )
        except (subprocess.CalledProcessError, OSError) as e:
            logger.debug(f"Failed to install UV via pip: {e}")
            return False
        if result.returncode != 0:
            return False
        logger.info("Successfully installed UV via pip")
        return True

    def _try_script_install(self) -> bool:
        installer_url = "https://astral.sh/uv/install.sh"
        try:
            result = subprocess.run(  # noqa: S603
                ["sh", "-c", f"curl -LsSf {installer_url} | sh"],  # noqa: S607
                capture_output=True,
                text=True,
                check=False,
            )
        except (subprocess.CalledProcessError, OSError) as e:
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

    def _has_migration_source(self) -> bool:
        """Check if there are any migration sources (Poetry, requirements.txt, setup.py, etc.)."""
        detected = detect_dependency_files(self.tools.repo_path)

        if detected.poetry_lock:
            return True
        if detected.pipfile or detected.pipfile_lock:
            return True
        if self._has_poetry_config():
            return True
        if detected.setup_py:
            return True

        requirements_files = list(self.tools.repo_path.rglob("requirements*.txt"))
        return bool(requirements_files)

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
        if not self._has_migration_source():
            return
        logger.info("Detected migration source, using uvx migrate-to-uv...")
        self.uv.run_uvx("migrate-to-uv")
        logger.info("Migration completed successfully")

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
            raise BoostSkippedError(msg)
        self._run_migration_if_needed()
        self._ensure_pyproject_exists()
        self._ensure_uv_config_present()
        self._generate_uv_lock()

    def commit_message(self) -> str:
        """Generate commit message for UV boost."""
        return "✨ Add UV dependency management"
