"""Local fixture-based e2e tests — no network, runs on every PR."""

from pathlib import Path

import pytest

from tests.e2e_utils import run_e2e_test, setup_local_fixture

_FIXTURES_DIR = Path(__file__).parent / "fixtures"

_FIXTURES = [
    "minimal-package",
    "setup-cfg-package",
    "pre-commit",
    "with-extras",
]


@pytest.mark.parametrize("fixture_name", _FIXTURES)
def test_local_fixture(fixture_name: str) -> None:
    repo_path = setup_local_fixture(fixture_name, fixtures_dir=_FIXTURES_DIR)
    run_e2e_test(repo_path)


@pytest.mark.e2e_local
def test_local_fixture_manual(fixture_name_arg: str) -> None:
    repo_path = setup_local_fixture(fixture_name_arg, fixtures_dir=_FIXTURES_DIR)
    run_e2e_test(repo_path)
