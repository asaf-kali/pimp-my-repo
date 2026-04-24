"""Remote repo e2e tests — clones real GitHub repos; runs only on main."""

import pytest

from tests.e2e_utils import run_e2e_test, setup_remote_repo

pytestmark = pytest.mark.e2e_remote


def test_remote_repo(e2e_url: str, e2e_rev: str | None, e2e_ty: bool) -> None:  # noqa: FBT001
    repo_path = setup_remote_repo(url=e2e_url, rev=e2e_rev)
    run_e2e_test(repo_path, ty=e2e_ty)
