"""UV boost implementation."""

import subprocess
import sys
from typing import Any

from loguru import logger
from tomlkit import TOMLDocument, document, dumps, loads, table

from pimp_my_repo.core.boost.base import Boost, BoostSkippedError
from pimp_my_repo.core.boost.uv.detector import detect_dependency_files


class UvBoost(Boost):
    """Boost for integrating UV dependency management."""

    def _run_uv(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        """Run a uv command in the repository directory."""
        cmd = ["uv", *args]
        return subprocess.run(  # noqa: S603
            cmd,
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=check,
        )

    def _run_uvx(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        """Run a uvx command in the repository directory."""
        cmd = ["uvx", *args]
        return subprocess.run(  # noqa: S603
            cmd,
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=check,
        )

    def _check_uv_installed(self) -> bool:
        """Check if UV is installed."""
        self._uv_version_failed = False
        try:
            result = self._run_uv("--version", check=False)
        except subprocess.CalledProcessError:
            self._uv_version_failed = True
            return False
        except OSError, FileNotFoundError:
            return False
        else:
            return result.returncode == 0

    def _install_uv(self) -> bool:
        """Attempt to install UV automatically."""
        logger.info("UV not found, attempting to install...")
        # Try pip install first
        try:
            result = subprocess.run(  # noqa: S603
                [sys.executable, "-m", "pip", "install", "uv"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                logger.info("Successfully installed UV via pip")
                return True
        except (subprocess.CalledProcessError, OSError) as e:
            logger.debug(f"Failed to install UV via pip: {e}")

        # Fallback to official installer script
        try:
            installer_url = "https://astral.sh/uv/install.sh"
            result = subprocess.run(  # noqa: S603
                ["sh", "-c", f"curl -LsSf {installer_url} | sh"],  # noqa: S607
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                logger.info("Successfully installed UV via official installer")
                return True
        except (subprocess.CalledProcessError, OSError) as e:
            logger.debug(f"Failed to install UV via official installer: {e}")

        logger.error("Failed to install UV automatically")
        return False

    def _read_pyproject(self) -> TOMLDocument:
        """Read existing pyproject.toml if it exists."""
        pyproject_path = self.repo_path / "pyproject.toml"
        if not pyproject_path.exists():
            return document()

        try:
            with pyproject_path.open(encoding="utf-8") as f:
                return loads(f.read())
        except (OSError, ValueError, UnicodeDecodeError) as e:
            logger.warning(f"Failed to read pyproject.toml: {e}")
            return document()

    def _write_pyproject(self, data: TOMLDocument) -> None:
        """Write pyproject.toml file."""
        pyproject_path = self.repo_path / "pyproject.toml"
        with pyproject_path.open("w", encoding="utf-8") as f:
            f.write(dumps(data))

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
        """Check if there are any migration sources (Poetry, requirements.txt, etc.)."""
        detected = detect_dependency_files(self.repo_path)
        pyproject_path = self.repo_path / "pyproject.toml"

        # Check for Poetry
        if detected.get("poetry.lock", False):
            return True
        if pyproject_path.exists():
            pyproject_data = self._read_pyproject()
            tool_section: Any = pyproject_data.get("tool", {})
            if isinstance(tool_section, dict) and tool_section.get("poetry"):
                return True

        # Check for requirements.txt files
        requirements_files = list(self.repo_path.rglob("requirements*.txt"))
        if requirements_files:
            return True

        # Check for other package managers
        return bool(detected.get("Pipfile", False) or detected.get("Pipfile.lock", False))

    def apply(self) -> None:
        """Create pyproject.toml if needed and migrate using uvx migrate-to-uv."""
        # Ensure uv is available
        uv_available = self._check_uv_installed()
        if not uv_available and getattr(self, "_uv_version_failed", False):
            uv_available = True

        if not uv_available and (not self._install_uv() or not self._check_uv_installed()):
            msg = "uv is not installed and could not be installed automatically"
            raise BoostSkippedError(msg)

        # Check if migration is needed
        if self._has_migration_source():
            logger.info("Detected migration source, using uvx migrate-to-uv...")
            try:
                # Run uvx migrate-to-uv to handle migration automatically
                self._run_uvx("migrate-to-uv")
                logger.info("Migration completed successfully")
            except subprocess.CalledProcessError as e:
                logger.error(f"Migration failed: {e.stderr}")
                raise

        # Ensure pyproject.toml exists (migrate-to-uv should create it, but ensure it's there)
        pyproject_path = self.repo_path / "pyproject.toml"
        if not pyproject_path.exists():
            logger.info("No pyproject.toml found, creating minimal one...")
            pyproject_data = document()
            # Try to infer project name from directory
            project_name = self.repo_path.name.lower().replace(" ", "-").replace("_", "-").strip("-")
            project_table = table()
            project_table["name"] = project_name
            project_table["version"] = "0.1.0"
            project_table["requires-python"] = ">=3.8"
            pyproject_data["project"] = project_table
            self._write_pyproject(pyproject_data)

        # Ensure UV config is present
        pyproject_data = self._read_pyproject()
        pyproject_data = self._ensure_uv_config(pyproject_data)
        self._write_pyproject(pyproject_data)

        # Generate uv.lock
        logger.info("Generating uv.lock...")
        try:
            self._run_uv("lock")
            logger.info("Successfully generated uv.lock")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to generate uv.lock: {e.stderr}")
            raise

    def commit_message(self) -> str:
        """Generate commit message for UV boost."""
        return "✨ Add UV dependency management"
