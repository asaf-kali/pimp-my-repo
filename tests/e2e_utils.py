"""Shared helpers for e2e tests (local fixtures and remote repos)."""

import shutil
import subprocess
from pathlib import Path

from loguru import logger

from pimp_my_repo.core.tools.repo import PMR_EMAIL

_PMR_ROOT = Path(__file__).parent.parent
_TMP_BASE = Path("/tmp/pmr")  # noqa: S108


# ── Setup helpers ─────────────────────────────────────────────────────────────


def setup_local_fixture(fixture_name: str, *, fixtures_dir: Path) -> Path:
    """Copy fixture files to /tmp/pmr/<name>/ and initialise as a git repo."""
    logger.info(f"Setting up local fixture '{fixture_name}' from '{fixtures_dir}'")
    src = fixtures_dir / fixture_name
    dest = _TMP_BASE / fixture_name
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    shutil.copytree(src, dest, dirs_exist_ok=True)
    _git_init(dest)
    _git_commit_all(dest, message="Initial commit")
    return dest


def setup_remote_repo(*, url: str, rev: str | None) -> Path:
    """Clone or reset a remote repo to /tmp/pmr/<name>/ and checkout rev."""
    logger.info(f"Setting up remote repo from '{url}' at rev '{rev or 'HEAD'}'")
    name = url.rstrip("/").split("/")[-1].removesuffix(".git")
    dest = _TMP_BASE / name
    if dest.exists():
        _reset_remote_repo(dest)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        _git(dest.parent, "clone", url, str(dest))
        _configure_git_identity(dest)
    if rev is not None:
        _git(dest, "checkout", rev)
    return dest


# ── Test entry point ──────────────────────────────────────────────────────────


def run_e2e_test(repo_path: Path) -> None:
    run_pmr(repo_path)
    logger.info("===================")
    logger.info("PMR run complete, verifying results...")
    assert_git_clean(repo_path)
    assert_ruff_passes(repo_path)
    assert_mypy_passes(repo_path)


# ── PMR runner ────────────────────────────────────────────────────────────────


def run_pmr(repo_path: Path) -> None:
    uv = shutil.which("uv")
    assert uv is not None, "uv not found on PATH"
    result = subprocess.run(  # noqa: S603
        [uv, "run", "pmr", "-p", str(repo_path)],
        cwd=_PMR_ROOT,
        check=False,
    )
    assert result.returncode == 0, f"pmr failed (exit {result.returncode})"


# ── Verification ──────────────────────────────────────────────────────────────


def assert_git_clean(repo_path: Path) -> None:
    result = _git(repo_path, "status", "--porcelain")
    assert not result.stdout.strip(), f"Unclean git state after pmr:\n{result.stdout}"


def assert_ruff_passes(repo_path: Path) -> None:
    ruff = str(_venv_exe(repo_path, "ruff"))
    _run_checked([ruff, "check", "."], cwd=repo_path)
    _run_checked([ruff, "format", "--check", "."], cwd=repo_path)


def assert_mypy_passes(repo_path: Path) -> None:
    _run_checked([str(_venv_exe(repo_path, "mypy")), "."], cwd=repo_path)


# ── Internal helpers ──────────────────────────────────────────────────────────


def _git_init(repo_path: Path) -> None:
    _git(repo_path, "init")
    _configure_git_identity(repo_path)


def _configure_git_identity(repo_path: Path) -> None:
    _git(repo_path, "config", "user.email", PMR_EMAIL)
    _git(repo_path, "config", "user.name", "pmr")


def _git_commit_all(repo_path: Path, *, message: str) -> None:
    _git(repo_path, "add", "-A")
    _git(repo_path, "commit", "--no-verify", "-m", message)


def _reset_remote_repo(repo_path: Path) -> None:
    git = _require_exe("git")
    _git(repo_path, "reset", "--hard", "HEAD")
    for branch in ("main", "master"):
        result = subprocess.run(  # noqa: S603
            [git, "checkout", branch],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            break
    _git(repo_path, "clean", "-fdx")
    subprocess.run(  # noqa: S603
        [git, "branch", "-D", "feat/pmr"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=False,
    )
    _git(repo_path, "pull")


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [_require_exe("git"), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )


def _require_exe(name: str) -> str:
    path = shutil.which(name)
    assert path is not None, f"{name} not found on PATH"
    return path


def _venv_exe(repo_path: Path, name: str) -> Path:
    exe = repo_path / ".venv" / "bin" / name
    assert exe.exists(), f"{name} not found in venv after pmr: {exe}"
    return exe


def _run_checked(cmd: list[str], *, cwd: Path) -> None:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)  # noqa: S603
    assert result.returncode == 0, f"{cmd[0]} failed:\n{result.stdout}\n{result.stderr}"
