import subprocess

from pimp_my_repo.main import main


def test_cli_is_working():
    result = subprocess.run(["pimp-my-repo"], capture_output=True, text=True)
    assert result.returncode == 0
    assert result.stdout.strip() == "Right now, there is no pimping going on."


def test_main_is_working():
    main()
