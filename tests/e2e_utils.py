"""Shared helpers for e2e tests (local fixtures and remote repos)."""

import re
import shutil
import subprocess
from pathlib import Path

from loguru import logger

from pimp_my_repo.core.tools.repo import PMR_EMAIL
from pimp_my_repo.core.tools.subprocess import run_command

_PMR_ROOT = Path(__file__).parent.parent
_TMP_BASE = Path("/tmp/pmr")  # noqa: S108

# Recipes PMR always creates (uv+ruff boosts always run; type checker varies)
_EXPECTED_JUST_RECIPES_BASE = {"install", "check-lock", "check-ruff", "lint"}
# lint runs pre-commit; skipped when repo had a pre-existing config PMR doesn't manage
_JUST_RECIPES_TO_RUN_BASE_WITH_PRECOMMIT = ("check-lock", "check-ruff", "lint")
_JUST_RECIPES_TO_RUN_BASE_WITHOUT_PRECOMMIT = ("check-lock", "check-ruff")


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
        logger.debug(f"Cloning remote repo from {url} to {dest}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        _git(dest.parent, "clone", url, str(dest))
        _configure_git_identity(dest)
    if rev is not None:
        logger.debug(f"Checking out rev {rev} in {dest}")
        _git(dest, "checkout", rev)
    return dest


# ── Test entry point ──────────────────────────────────────────────────────────


def run_e2e_test(repo_path: Path, *, pmr_args: list[str] | None = None) -> None:
    pmr_args = pmr_args or []
    ty = "--ty" in pmr_args
    run_pmr(repo_path, pmr_args=pmr_args)
    logger.info("=========================================================")
    logger.info("PMR run complete, verifying results...")
    assert_git_clean(repo_path)
    assert_just_install_works(repo_path)
    assert_just_commands_work(repo_path, ty=ty)
    assert_ruff_passes(repo_path)
    if ty:
        assert_ty_passes(repo_path)
    else:
        assert_mypy_passes(repo_path)
    assert_pre_commit_passes(repo_path)


# ── PMR runner ────────────────────────────────────────────────────────────────


def run_pmr(repo_path: Path, *, pmr_args: list[str] | None = None) -> None:
    uv = shutil.which("uv")
    assert uv is not None, "uv not found on PATH"
    cmd = [uv, "run", "pmr", "-p", str(repo_path), *(pmr_args or [])]
    result = subprocess.run(cmd, cwd=_PMR_ROOT, check=False)  # noqa: S603
    assert result.returncode == 0, f"pmr failed (exit {result.returncode})"


# ── Verification ──────────────────────────────────────────────────────────────


def assert_git_clean(repo_path: Path) -> None:
    result = _git(repo_path, "status", "--porcelain")
    assert not result.stdout.strip(), f"Unclean git state after pmr:\n{result.stdout}"


def assert_ruff_passes(repo_path: Path) -> None:
    ruff = str(_venv_exe(repo_path, "ruff"))
    run_command([ruff, "check", "."], cwd=repo_path)
    run_command([ruff, "format", "--check", "."], cwd=repo_path)


def assert_mypy_passes(repo_path: Path) -> None:
    run_command([str(_venv_exe(repo_path, "mypy")), "."], cwd=repo_path)


def assert_ty_passes(repo_path: Path) -> None:
    run_command([str(_venv_exe(repo_path, "ty")), "check", "."], cwd=repo_path)


def assert_just_install_works(repo_path: Path) -> None:
    """Assert justfile exists with a working install recipe.

    Removes .venv and re-runs `just install` from scratch to verify the full
    install flow (uv sync --all-groups + pre-commit install) works correctly.
    Asserts .venv is recreated. When PMR manages pre-commit, also asserts the
    git hook is installed in .git/hooks/.
    """
    just = _require_exe("just")
    justfile_path = repo_path / "justfile"
    assert justfile_path.exists(), "justfile not created after pmr"
    assert "install:" in justfile_path.read_text(encoding="utf-8"), "justfile missing install recipe"

    venv_path = repo_path / ".venv"
    if venv_path.exists():
        shutil.rmtree(venv_path)
    run_command([just, "install"], cwd=repo_path)

    assert venv_path.exists(), ".venv not created after `just install`"
    if _pmr_manages_pre_commit(repo_path):
        hook_path = repo_path / ".git" / "hooks" / "pre-commit"
        assert hook_path.exists(), "pre-commit hook not installed in .git/hooks/ after `just install`"


def assert_just_commands_work(repo_path: Path, *, ty: bool = False) -> None:
    """Assert all PMR-generated just recipes exist and pass."""
    just = _require_exe("just")
    justfile_path = repo_path / "justfile"
    assert justfile_path.exists(), "justfile not created after pmr"
    recipes = _get_just_recipes(justfile_path)
    checker_recipe = "check-ty" if ty else "check-mypy"
    expected = _EXPECTED_JUST_RECIPES_BASE | {checker_recipe}
    missing = expected - recipes
    assert not missing, f"justfile missing expected recipes: {sorted(missing)}"
    extra_recipes = (checker_recipe,)
    recipes_to_run = (
        _JUST_RECIPES_TO_RUN_BASE_WITH_PRECOMMIT + extra_recipes
        if _pmr_manages_pre_commit(repo_path)
        else _JUST_RECIPES_TO_RUN_BASE_WITHOUT_PRECOMMIT + extra_recipes
    )
    for recipe in recipes_to_run:
        run_command([just, recipe], cwd=repo_path)


def assert_pre_commit_passes(repo_path: Path) -> None:
    if not _pmr_manages_pre_commit(repo_path):
        logger.info("Pre-existing .pre-commit-config.yaml not managed by PMR — skipping pre-commit validation")
        return
    config_path = repo_path / ".pre-commit-config.yaml"
    assert config_path.exists(), ".pre-commit-config.yaml not found after pmr"
    run_command([str(_venv_exe(repo_path, "pre-commit")), "run", "--all-files"], cwd=repo_path)


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
    logger.debug(f"Resetting existing repo at {repo_path} for reuse")
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


def _pmr_manages_pre_commit(repo_path: Path) -> bool:
    """Return True if the pre-commit config was created by PMR (has the PMR marker)."""
    config_path = repo_path / ".pre-commit-config.yaml"
    return config_path.exists() and "pimp-my-repo:pre-commit" in config_path.read_text(encoding="utf-8")


def _get_just_recipes(justfile_path: Path) -> set[str]:
    recipes: set[str] = set()
    for line in justfile_path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([a-zA-Z0-9][a-zA-Z0-9_-]*)", line)
        if m and ":=" not in line and ":" in line:
            recipes.add(m.group(1))
    return recipes
