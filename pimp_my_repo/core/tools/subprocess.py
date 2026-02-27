"""Shared subprocess execution utility."""

import subprocess
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from pathlib import Path


def run_command(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
    log_on_error: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run a command capturing stdout and stderr.

    Args:
        cmd: Command and arguments to run.
        cwd: Working directory for the command. Defaults to the current directory.
        check: If True and the command exits non-zero, raise CalledProcessError.
        log_on_error: If True, log stderr/stdout before raising on non-zero exit.

    """
    result = subprocess.run(  # noqa: S603
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 and check:
        if log_on_error:
            output = (result.stderr or result.stdout).strip()
            logger.error(f"Command {cmd!r} failed: {output}")
        raise subprocess.CalledProcessError(result.returncode, cmd, result.stdout, result.stderr)
    return result
