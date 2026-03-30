"""Python version resolution for UV boost."""

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger

from pimp_my_repo.core.tools.subprocess import run_command

if TYPE_CHECKING:
    from pathlib import Path

_VENV_DIRS = [".venv", "venv", "env", ".env"]
_VENV_PYTHON_PATHS = ["bin/python", "bin/python3", "Scripts/python.exe"]


@dataclass
class PythonVersion:
    major: int
    minor: int


def resolve_requires_python(*, repo_path: Path) -> str | None:
    """Resolve requires-python value: prefer venv, then uv.lock, then vermin.

    Returns None if no version can be determined — caller should skip setting requires-python.
    Priority: venv (actual running Python) > uv.lock (already-resolved constraint) > vermin (code syntax).
    """
    logger.debug(f"Resolving requires-python for {repo_path}")
    version = _detect_venv_python_version(repo_path=repo_path)
    if version is not None:
        logger.debug(f"Python version from venv: {version.major}.{version.minor}")
        return f">={version.major}.{version.minor}"

    version = _detect_from_uv_lock(repo_path=repo_path)
    if version is not None:
        logger.debug(f"Python version from uv.lock: {version.major}.{version.minor}")
        return f">={version.major}.{version.minor}"

    version = _detect_vermin_min_version(repo_path=repo_path)
    if version is not None:
        logger.debug(f"Python version from vermin: {version.major}.{version.minor}")
        return f">={version.major}.{version.minor}"

    logger.debug("No Python version detected from any source")
    return None


def _detect_venv_python_version(*, repo_path: Path) -> PythonVersion | None:
    logger.debug(f"Checking for venv in {repo_path}")
    for venv_dir in _VENV_DIRS:
        venv_path = repo_path / venv_dir
        if not venv_path.is_dir():
            logger.trace(f"Venv dir not found: {venv_path}")
            continue
        version = _check_venv_dir(venv_path=venv_path, repo_path=repo_path)
        if version is not None:
            return version
    return None


def _check_venv_dir(*, venv_path: Path, repo_path: Path) -> PythonVersion | None:
    logger.trace(f"Checking venv at {venv_path}")
    for python_rel in _VENV_PYTHON_PATHS:
        version = _check_python_exe(python_exe=venv_path / python_rel, repo_path=repo_path)
        if version is not None:
            return version
    logger.trace(f"No Python executable found in {venv_path}")
    return None


def _check_python_exe(*, python_exe: Path, repo_path: Path) -> PythonVersion | None:
    if not python_exe.exists():
        logger.trace(f"Python exe not found: {python_exe}")
        return None
    logger.trace(f"Running {python_exe} --version")
    try:
        result = run_command([str(python_exe), "--version"], cwd=repo_path, check=False)
    except OSError as e:
        logger.trace(f"Failed to run {python_exe}: {e}")
        return None
    output = result.stdout.strip()
    match = re.match(r"Python (\d+)\.(\d+)", output)
    if not match:
        logger.trace(f"Unexpected output from {python_exe}: {output!r}")
        return None
    version = PythonVersion(major=int(match.group(1)), minor=int(match.group(2)))
    logger.trace(f"Detected version {version.major}.{version.minor} from {python_exe}")
    return version


def _detect_from_uv_lock(*, repo_path: Path) -> PythonVersion | None:
    uv_lock_path = repo_path / "uv.lock"
    if not uv_lock_path.exists():
        logger.debug(f"uv.lock not found at {uv_lock_path}")
        return None
    logger.debug(f"Reading requires-python from {uv_lock_path}")
    try:
        content = uv_lock_path.read_text(encoding="utf-8")
    except OSError as e:
        logger.debug(f"Failed to read uv.lock: {e}")
        return None
    match = re.search(r'^requires-python\s*=\s*">=(\d+)\.(\d+)', content, re.MULTILINE)
    if not match:
        logger.debug("No requires-python constraint found in uv.lock")
        return None
    version = PythonVersion(major=int(match.group(1)), minor=int(match.group(2)))
    logger.debug(f"Found requires-python >={version.major}.{version.minor} in uv.lock")
    return version


def _detect_vermin_min_version(*, repo_path: Path) -> PythonVersion | None:
    logger.debug(f"Running vermin on {repo_path}")
    try:
        result = run_command(["vermin", str(repo_path)], cwd=repo_path, check=False)
    except OSError:
        logger.debug("vermin not found, skipping version detection")
        return None
    output = result.stdout or ""
    logger.trace(f"vermin output: {output!r}")
    match = re.search(r"Minimum required versions:.*?3\.(\d+)", output)
    if not match:
        logger.debug("vermin did not report a minimum Python 3 version")
        return None
    version = PythonVersion(major=3, minor=int(match.group(1)))
    logger.debug(f"vermin detected minimum version 3.{version.minor}")
    return version
