"""Shared subprocess execution utility."""

import os
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class CommandResult:
    """Result of a subprocess command execution."""

    cmd: list[str]
    returncode: int
    stdout: str
    stderr: str

    def log_output(self, *, level: str = "TRACE") -> None:
        """Log stdout and stderr separately at the given level (if non-empty)."""
        std_out = self.stdout.strip()
        std_err = self.stderr.strip()
        if std_out:
            logger.log(level, f"stdout: {std_out}")
        if std_err:
            logger.log(level, f"stderr: {std_err}")


def run_command(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
    log_on_error: bool = True,
) -> CommandResult:
    """Run a command capturing stdout and stderr.

    Args:
        cmd: Command and arguments to run.
        cwd: Working directory for the command. Defaults to the current directory.
        check: If True and the command exits non-zero, raise CalledProcessError.
        log_on_error: If True (default), log stderr/stdout at TRACE on non-zero exit.
            If False, only log the exit code.

    """
    env_vars = os.environ.copy()
    env_vars.pop("VIRTUAL_ENV", None)  # Ensure subprocess doesn't inherit virtualenv
    env_vars.pop("VIRTUAL_ENV_PROMPT", None)
    logger.debug(f"Running {cmd}")
    raw = subprocess.run(  # noqa: S603
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        env=env_vars,
    )
    result = CommandResult(cmd=cmd, returncode=raw.returncode, stdout=raw.stdout, stderr=raw.stderr)
    if result.returncode != 0:
        _handle_failure(result, check=check, log_on_error=log_on_error)
    return result


def _handle_failure(result: CommandResult, *, check: bool, log_on_error: bool) -> None:
    _log_failure(result, log_on_error=log_on_error)
    if check:
        raise subprocess.CalledProcessError(result.returncode, result.cmd, result.stdout, result.stderr)


def _log_failure(result: CommandResult, *, log_on_error: bool) -> None:
    logger.debug(f"exit={result.returncode}")
    if not log_on_error:
        return
    result.log_output()
