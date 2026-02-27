"""Registry of all available boost classes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pimp_my_repo.core.boosts.gitignore import GitignoreBoost
from pimp_my_repo.core.boosts.justfile import JustfileBoost
from pimp_my_repo.core.boosts.mypy import MypyBoost
from pimp_my_repo.core.boosts.pre_commit import PreCommitBoost
from pimp_my_repo.core.boosts.ruff import RuffBoost
from pimp_my_repo.core.boosts.uv import UvBoost

if TYPE_CHECKING:
    from pimp_my_repo.core.boosts.base import Boost

_ALL_BOOSTS: list[type[Boost]] = [
    GitignoreBoost,
    UvBoost,
    RuffBoost,
    MypyBoost,
    PreCommitBoost,
    JustfileBoost,
]


def get_all_boosts() -> list[type[Boost]]:
    """Get all available boost classes."""
    return _ALL_BOOSTS.copy()
