"""BoostTools dataclass for boost operations."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from pimp_my_repo.core.tools.git import GitController
from pimp_my_repo.core.tools.http import HttpController
from pimp_my_repo.core.tools.pyproject import PyProjectController
from pimp_my_repo.core.tools.uv import UvController

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class BoostTools:
    """Collection of tool controllers for boost operations."""

    git: GitController
    uv: UvController
    http: HttpController
    pyproject: PyProjectController

    @property
    def repo_path(self) -> Path:
        """Get the repository path from any controller."""
        return self.git.repo_path

    @classmethod
    def create(cls, repo_path: Path) -> BoostTools:
        """Create a BoostTools instance for the given repository path."""
        return cls(
            git=GitController(repo_path=repo_path),
            uv=UvController(repo_path=repo_path),
            http=HttpController(),
            pyproject=PyProjectController(repo_path=repo_path),
        )
