"""Boost modules for pimp-my-repo."""

from pimp_my_repo.core.boost.base import Boost
from pimp_my_repo.core.boost.gitignore import GitignoreBoost
from pimp_my_repo.core.boost.justfile import JustfileBoost
from pimp_my_repo.core.boost.mypy import MypyBoost
from pimp_my_repo.core.boost.pre_commit import PreCommitBoost
from pimp_my_repo.core.boost.ruff import RuffBoost
from pimp_my_repo.core.boost.uv import UvBoost

__all__ = [
    "Boost",
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
