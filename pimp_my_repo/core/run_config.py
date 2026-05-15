"""Run configuration dataclass for user-supplied options."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class RunConfig:
    skip_config: bool = False
    branch: str | None = None
    repo_path: Path | None = None
