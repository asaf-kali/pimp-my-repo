"""Registry of all available boost classes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pimp_my_repo.core.boosts.gitignore import GitignoreBoost
from pimp_my_repo.core.boosts.justfile import JustfileBoost
from pimp_my_repo.core.boosts.mypy import DmypyBoost, MypyBoost
from pimp_my_repo.core.boosts.pre_commit import PreCommitBoost
from pimp_my_repo.core.boosts.ruff import RuffBoost
from pimp_my_repo.core.boosts.ty import TyBoost
from pimp_my_repo.core.boosts.uv import UvBoost

if TYPE_CHECKING:
    from pimp_my_repo.core.boosts.base import Boost

# Boosts that run by default (no --only flag needed).
_DEFAULT_BOOSTS: list[type[Boost]] = [
    GitignoreBoost,
    UvBoost,
    RuffBoost,
    MypyBoost,
    JustfileBoost,
    PreCommitBoost,
]

# Boosts that must be explicitly requested via --only.
_OPT_IN_BOOSTS: list[type[Boost]] = [
    DmypyBoost,
    TyBoost,
]


def get_all_boosts() -> list[type[Boost]]:
    """Get default boost classes (run when no --only flag is given)."""
    return _DEFAULT_BOOSTS.copy()


def get_opt_in_boosts() -> list[type[Boost]]:
    """Get opt-in boost classes (must be requested explicitly via --only)."""
    return _OPT_IN_BOOSTS.copy()
