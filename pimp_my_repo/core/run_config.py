"""Run configuration dataclass for user-supplied options."""

from dataclasses import dataclass


@dataclass
class RunConfig:
    skip_config: bool = False
