"""Boost modules for pimp-my-repo."""

from pimp_my_repo.core.boosts.base import Boost, BoostSkippedError
from pimp_my_repo.core.boosts.gitignore import GitignoreBoost
from pimp_my_repo.core.boosts.justfile import JustfileBoost
from pimp_my_repo.core.boosts.mypy import MypyBoost
from pimp_my_repo.core.boosts.pre_commit import PreCommitBoost
from pimp_my_repo.core.boosts.ruff import RuffBoost
from pimp_my_repo.core.boosts.uv import UvBoost

__all__ = [
    "Boost",
    "BoostSkippedError",
    "GitignoreBoost",
    "JustfileBoost",
    "MypyBoost",
    "PreCommitBoost",
    "RuffBoost",
    "UvBoost",
    "get_all_boosts",
]

# Registry of all boost classes
_ALL_BOOSTS = [
    GitignoreBoost,
    UvBoost,
    RuffBoost,
    MypyBoost,
    PreCommitBoost,
    JustfileBoost,
]


def get_all_boosts() -> list[type[Boost]]:
    """Get all available boost classes.

    Returns:
        List of boost classes

    """
    return _ALL_BOOSTS.copy()
