from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pimp_my_repo.core.tools.git import GitController


@dataclass
class BoostTools:
    git_controller: GitController
