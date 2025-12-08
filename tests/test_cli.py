import subprocess

from pimp_my_repo.main import main


def test_cli_is_working() -> None:
    result = subprocess.run(
        ["pimp-my-repo"],  # noqa: S607
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0  # noqa: S101
    assert result.stdout.strip() == "Right now, there is no pimping going on."  # noqa: S101


def test_main_is_working() -> None:
    main()
