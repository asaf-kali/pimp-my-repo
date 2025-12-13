import subprocess

import pytest

from pimp_my_repo.cli.main import main


def test_cli_is_working() -> None:
    result = subprocess.run(
        ["pimp-my-repo"],  # noqa: S607
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0  # noqa: S101
    assert result.stdout.strip() == "Pimping repository at: ."  # noqa: S101


def test_main_is_working() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 0  # noqa: S101
