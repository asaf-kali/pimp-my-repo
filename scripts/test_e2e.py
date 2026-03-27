# ruff: noqa: INP001
"""End-to-end test for pimp-my-repo: clone, pimp, verify."""

import logging
import shutil
import subprocess
from pathlib import Path

import typer
from rich.logging import RichHandler

from pimp_my_repo.core.tools.repo import PMR_EMAIL

_PMR_ROOT = Path(__file__).parent.parent
_TMP_DIR = Path("/tmp/pmr")  # noqa: S108

logger = logging.getLogger(__name__)
app = typer.Typer(help="End-to-end test for pimp-my-repo.")

_REPO_URL_ARG = typer.Argument(..., help="Git URL of the repository to test")
_VERBOSE_ARG = typer.Option(
    False,  # noqa: FBT003
    "--verbose",
    "-v",
    help="Show debug logs",
)


class E2EError(Exception):
    """Raised when an e2e verification step fails."""


def _setup_logging(*, verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, markup=True)],
    )


def _require_exe(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        msg = f"Required executable not found: {name}"
        raise E2EError(msg)
    return path


def _run(
    args: list[str],
    *,
    cwd: Path,
    check: bool = True,
    assert_clean_stderr: bool = False,
) -> subprocess.CompletedProcess[str]:
    display = " ".join(args)
    logger.info("[bold]$[/bold] %s", display)
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)  # noqa: S603
    if result.stdout.strip():
        logger.info("%s", result.stdout.strip())
    if result.stderr.strip():
        logger.warning("%s", result.stderr.strip())
    if check and result.returncode != 0:
        msg = f"Command failed (exit {result.returncode}): {display}"
        raise E2EError(msg)
    if assert_clean_stderr and result.stderr.strip():
        msg = f"Unexpected stderr from: {display}\n{result.stderr.strip()}"
        raise E2EError(msg)
    return result


def _extract_repo_name(repo_url: str) -> str:
    return repo_url.rstrip("/").split("/")[-1].removesuffix(".git")


def _clone_repo(*, repo_url: str, dest: Path) -> None:
    logger.info("Cloning [cyan]%s[/cyan]...", repo_url)
    dest.parent.mkdir(parents=True, exist_ok=True)
    _run([_require_exe("git"), "clone", repo_url, str(dest)], cwd=dest.parent)


def _checkout_default_branch(repo_path: Path) -> None:
    git = _require_exe("git")
    for branch in ("main", "master"):
        result = _run([git, "checkout", branch], cwd=repo_path, check=False)
        if result.returncode == 0:
            return
    msg = "Could not checkout main or master branch"
    raise E2EError(msg)


def _delete_branch_if_exists(*, repo_path: Path, branch: str) -> None:
    git = _require_exe("git")
    result = _run([git, "branch", "--list", branch], cwd=repo_path)
    if not result.stdout.strip():
        return
    _run([git, "branch", "-D", branch], cwd=repo_path)


def _reset_repo(repo_path: Path) -> None:
    logger.info("Resetting repo at [cyan]%s[/cyan]...", repo_path)
    git = _require_exe("git")
    _run([git, "reset", "--hard", "HEAD"], cwd=repo_path)
    _checkout_default_branch(repo_path)
    _run([git, "reset", "--hard", "HEAD"], cwd=repo_path)
    _run([git, "clean", "-fdx"], cwd=repo_path)
    _delete_branch_if_exists(repo_path=repo_path, branch="feat/pmr")
    _run([git, "pull"], cwd=repo_path)


def _prepare_repo(repo_url: str) -> Path:
    repo_name = _extract_repo_name(repo_url)
    repo_path = _TMP_DIR / repo_name
    if repo_path.exists():
        _reset_repo(repo_path)
    else:
        _clone_repo(repo_url=repo_url, dest=repo_path)
    return repo_path


def _configure_git_identity(repo_path: Path) -> None:
    """Set a minimal git user identity so commits work in CI (where global config may be absent)."""
    git = _require_exe("git")
    logger.debug("Configuring git user identity for repo...")
    _run([git, "config", "user.email", PMR_EMAIL], cwd=repo_path)
    _run([git, "config", "user.name", "pmr"], cwd=repo_path)


def _run_pmr(repo_path: Path) -> None:
    _configure_git_identity(repo_path)
    logger.info("Running [bold]pmr[/bold] on [cyan]%s[/cyan]...", repo_path)
    args = [_require_exe("uv"), "run", "pmr", "-p", str(repo_path)]
    logger.info("[bold]$[/bold] %s", " ".join(args))
    result = subprocess.run(args, cwd=_PMR_ROOT, check=False)  # noqa: S603
    if result.returncode != 0:
        msg = f"pmr failed (exit {result.returncode})"
        raise E2EError(msg)


def _assert_git_clean(repo_path: Path) -> None:
    result = _run([_require_exe("git"), "status", "--porcelain"], cwd=repo_path)
    if result.stdout.strip():
        msg = f"Git status is not clean after pmr:\n{result.stdout}"
        raise E2EError(msg)
    logger.info("[green]Git status is clean ✓[/green]")


def _venv_exe(repo_path: Path, tool: str) -> str:
    exe = repo_path / ".venv" / "bin" / tool
    if not exe.exists():
        msg = f"Venv executable not found: {exe}"
        raise E2EError(msg)
    return str(exe)


def _run_ruff_checks(repo_path: Path) -> None:
    ruff = _venv_exe(repo_path, "ruff")
    _run([ruff, "check", "."], cwd=repo_path, assert_clean_stderr=True)
    logger.info("[green]ruff check ✓[/green]")
    _run([ruff, "format", "--check", "."], cwd=repo_path, assert_clean_stderr=True)
    logger.info("[green]ruff format ✓[/green]")


def _run_mypy_checks(repo_path: Path) -> None:
    mypy = _venv_exe(repo_path, "mypy")
    _run([mypy, "."], cwd=repo_path)
    logger.info("[green]mypy ✓[/green]")


def _run_verification_checks(repo_path: Path) -> None:
    logger.info("[bold]Running verification checks...[/bold]")
    _run_ruff_checks(repo_path)
    _run_mypy_checks(repo_path)


@app.command()
def run(
    repo_url: str = _REPO_URL_ARG,
    verbose: bool = _VERBOSE_ARG,  # noqa: FBT001
) -> None:
    """Clone a repo, run pmr, and verify all checks pass."""
    _setup_logging(verbose=verbose)
    try:
        repo_path = _prepare_repo(repo_url)
        _run_pmr(repo_path)
        _assert_git_clean(repo_path)
        _run_verification_checks(repo_path)
        logger.info("[bold green]✓ All checks passed![/bold green]")
    except E2EError as exc:
        logger.exception("E2E test failed")
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    app()
