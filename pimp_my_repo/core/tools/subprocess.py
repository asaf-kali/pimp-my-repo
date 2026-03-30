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

    @property
    def output(self) -> str:
        """Return stderr if non-empty, else stdout, stripped."""
        return (self.stderr or self.stdout).strip()

    def log_output(self, *, level: str = "debug") -> None:
        """Log the command output at the given level (if non-empty)."""
        text = self.output
        if not text:
            return
        log_fn = getattr(logger, level)
        log_fn(text)


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
        log_on_error: If True (default), log stderr/stdout at DEBUG on non-zero exit.
            If False, only log the exit code.

    """
    env_vars = os.environ.copy()
    env_vars.pop("VIRTUAL_ENV", None)  # Ensure subprocess doesn't inherit virtualenv
    env_vars.pop("VIRTUAL_ENV_PROMPT", None)
    logger.debug(f"$ {' '.join(cmd)}" + (f"  [cwd={cwd}]" if cwd else ""))
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
        if log_on_error:
            if result.output:
                logger.debug(f"exit={result.returncode}: {result.output}")
            else:
                logger.debug(f"exit={result.returncode}")
        else:
            logger.debug(f"exit={result.returncode}")
        if check:
            raise subprocess.CalledProcessError(result.returncode, cmd, raw.stdout, raw.stderr)
    return result
