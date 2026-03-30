"""Shared subprocess execution utility."""

import os
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
) -> subprocess.CompletedProcess[str]:
    """Run a command capturing stdout and stderr.

    Args:
        cmd: Command and arguments to run.
        cwd: Working directory for the command. Defaults to the current directory.
        check: If True and the command exits non-zero, raise CalledProcessError.

    """
    env_vars = os.environ.copy()
    env_vars.pop("VIRTUAL_ENV", None)  # Ensure subprocess doesn't inherit virtualenv
    env_vars.pop("VIRTUAL_ENV_PROMPT", None)
    logger.debug(f"$ {' '.join(cmd)}" + (f"  [cwd={cwd}]" if cwd else ""))
    result = subprocess.run(  # noqa: S603
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        env=env_vars,
    )
    if result.returncode != 0:
        output = (result.stderr or result.stdout).strip()
        if output:
            logger.debug(f"exit={result.returncode}: {output}")
        else:
            logger.debug(f"exit={result.returncode}")
        if check:
            raise subprocess.CalledProcessError(result.returncode, cmd, result.stdout, result.stderr)
    return result
