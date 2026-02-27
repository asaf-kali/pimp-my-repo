"""Tests for Gitignore boost implementation."""

import urllib.error
from dataclasses import dataclass
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from pimp_my_repo.core.boosts.gitignore import (
    _ALWAYS_TEMPLATES,
    _GITIGNORE_HEADER,
    GitignoreBoost,
)

if TYPE_CHECKING:
    from collections.abc import Generator

    from pimp_my_repo.core.tools.boost_tools import BoostTools
    from tests.repo_controller import RepositoryController


@pytest.fixture
def gitignore_boost(boost_tools: BoostTools) -> GitignoreBoost:
    return GitignoreBoost(boost_tools)


@pytest.fixture
def urlopen_returning_pyc_content(gitignore_boost: GitignoreBoost) -> Generator[GitignoreBoost]:
    """Yield a GitignoreBoost where http.request returns fake gitignore content."""
    fake_content = "*.pyc\n__pycache__/\n"
    with patch.object(gitignore_boost.http, "request", return_value=fake_content):
        yield gitignore_boost


@pytest.fixture
def urlopen_raising_url_error(gitignore_boost: GitignoreBoost) -> Generator[GitignoreBoost]:
    """Yield a GitignoreBoost where http.request raises URLError."""
    with patch.object(gitignore_boost.http, "request", side_effect=urllib.error.URLError("network error")):
        yield gitignore_boost


@pytest.fixture
def urlopen_raising_oserror(gitignore_boost: GitignoreBoost) -> Generator[GitignoreBoost]:
    """Yield a GitignoreBoost where http.request raises OSError."""
    with patch.object(gitignore_boost.http, "request", side_effect=OSError("connection refused")):
        yield gitignore_boost


@dataclass
class CapturingUrlBoost:
    """GitignoreBoost paired with the http.request mock for URL assertion tests."""

    boost: GitignoreBoost
    mock_request: MagicMock


@pytest.fixture
def urlopen_capturing_url(gitignore_boost: GitignoreBoost) -> Generator[CapturingUrlBoost]:
    """Yield a GitignoreBoost and the http.request mock for URL assertion tests."""
    with patch.object(gitignore_boost.http, "request", return_value="") as mock_request:
        yield CapturingUrlBoost(boost=gitignore_boost, mock_request=mock_request)


_FAKE_GITIGNORE = "*.pyc\n__pycache__/\n.venv/\n"


@dataclass
class PatchedGitignoreApply:
    """Pre-patched GitignoreBoost with all external calls mocked for apply()."""

    boost: GitignoreBoost
    mock_fetch: MagicMock
    mock_add: MagicMock
    mock_commit: MagicMock
    mock_reset: MagicMock


@pytest.fixture
def patched_gitignore_apply(gitignore_boost: GitignoreBoost) -> Generator[PatchedGitignoreApply]:
    """Yield a GitignoreBoost with fetch and git calls pre-mocked to succeed."""
    with (
        patch.object(gitignore_boost, "_fetch_gitignore", return_value=_FAKE_GITIGNORE) as mock_fetch,
        patch.object(gitignore_boost.tools.git, "add") as mock_add,
        patch.object(gitignore_boost.tools.git, "commit") as mock_commit,
        patch.object(gitignore_boost.tools.git, "reset_tracking") as mock_reset,
    ):
        yield PatchedGitignoreApply(
            boost=gitignore_boost,
            mock_fetch=mock_fetch,
            mock_add=mock_add,
            mock_commit=mock_commit,
            mock_reset=mock_reset,
        )


@pytest.fixture
def patched_gitignore_apply_fetch_fails(gitignore_boost: GitignoreBoost) -> Generator[PatchedGitignoreApply]:
    """Yield a GitignoreBoost where fetch returns None (simulating API failure)."""
    with (
        patch.object(gitignore_boost, "_fetch_gitignore", return_value=None) as mock_fetch,
        patch.object(gitignore_boost.tools.git, "add") as mock_add,
        patch.object(gitignore_boost.tools.git, "commit") as mock_commit,
        patch.object(gitignore_boost.tools.git, "reset_tracking") as mock_reset,
    ):
        yield PatchedGitignoreApply(
            boost=gitignore_boost,
            mock_fetch=mock_fetch,
            mock_add=mock_add,
            mock_commit=mock_commit,
            mock_reset=mock_reset,
        )


@dataclass
class GitignoreBoostWithMockedReset:
    """GitignoreBoost paired with the reset_tracking mock."""

    boost: GitignoreBoost
    mock_reset: MagicMock


@pytest.fixture
def gitignore_boost_with_mocked_reset(gitignore_boost: GitignoreBoost) -> Generator[GitignoreBoostWithMockedReset]:
    """Yield a GitignoreBoost with reset_tracking mocked, plus the mock."""
    with patch.object(gitignore_boost.tools.git, "reset_tracking") as mock_reset:
        yield GitignoreBoostWithMockedReset(boost=gitignore_boost, mock_reset=mock_reset)


# =============================================================================
# TEMPLATE DETECTION
# =============================================================================


def test_always_includes_base_templates(gitignore_boost: GitignoreBoost) -> None:
    templates = gitignore_boost._detect_templates()  # noqa: SLF001
    for t in _ALWAYS_TEMPLATES:
        assert t in templates


@pytest.mark.smoke
def test_detects_python_from_pyproject(mock_repo: RepositoryController, gitignore_boost: GitignoreBoost) -> None:
    mock_repo.add_file("pyproject.toml", "[project]\nname = 'test'\n")
    assert "python" in gitignore_boost._detect_templates()  # noqa: SLF001


def test_detects_python_from_setup_py(mock_repo: RepositoryController, gitignore_boost: GitignoreBoost) -> None:
    mock_repo.add_file("setup.py", "from setuptools import setup")
    assert "python" in gitignore_boost._detect_templates()  # noqa: SLF001


def test_detects_python_from_requirements_txt(mock_repo: RepositoryController, gitignore_boost: GitignoreBoost) -> None:
    mock_repo.add_file("requirements.txt", "requests")
    assert "python" in gitignore_boost._detect_templates()  # noqa: SLF001


def test_detects_node_from_package_json(mock_repo: RepositoryController, gitignore_boost: GitignoreBoost) -> None:
    mock_repo.add_file("package.json", '{"name": "test"}')
    assert "node" in gitignore_boost._detect_templates()  # noqa: SLF001


def test_detects_rust_from_cargo_toml(mock_repo: RepositoryController, gitignore_boost: GitignoreBoost) -> None:
    mock_repo.add_file("Cargo.toml", '[package]\nname = "test"')
    assert "rust" in gitignore_boost._detect_templates()  # noqa: SLF001


def test_detects_go_from_go_mod(mock_repo: RepositoryController, gitignore_boost: GitignoreBoost) -> None:
    mock_repo.add_file("go.mod", "module example.com/mymod\ngo 1.21")
    assert "go" in gitignore_boost._detect_templates()  # noqa: SLF001


def test_detects_java_maven_from_pom_xml(mock_repo: RepositoryController, gitignore_boost: GitignoreBoost) -> None:
    mock_repo.add_file("pom.xml", "<project/>")
    templates = gitignore_boost._detect_templates()  # noqa: SLF001
    assert "java" in templates
    assert "maven" in templates


def test_detects_java_gradle_from_build_gradle(
    mock_repo: RepositoryController, gitignore_boost: GitignoreBoost
) -> None:
    mock_repo.add_file("build.gradle", "plugins { id 'java' }")
    templates = gitignore_boost._detect_templates()  # noqa: SLF001
    assert "java" in templates
    assert "gradle" in templates


def test_no_language_detected_for_plain_repo(gitignore_boost: GitignoreBoost) -> None:
    templates = gitignore_boost._detect_templates()  # noqa: SLF001
    assert "python" not in templates
    assert "node" not in templates


def test_detects_multiple_languages(mock_repo: RepositoryController, gitignore_boost: GitignoreBoost) -> None:
    mock_repo.add_file("pyproject.toml", "")
    mock_repo.add_file("package.json", "{}")
    templates = gitignore_boost._detect_templates()  # noqa: SLF001
    assert "python" in templates
    assert "node" in templates


# =============================================================================
# FETCH GITIGNORE
# =============================================================================


@pytest.mark.smoke
def test_returns_content_on_success(urlopen_returning_pyc_content: GitignoreBoost) -> None:
    result = urlopen_returning_pyc_content._fetch_gitignore(["python"])  # noqa: SLF001
    assert result == "*.pyc\n__pycache__/\n"


def test_returns_none_on_url_error(urlopen_raising_url_error: GitignoreBoost) -> None:
    result = urlopen_raising_url_error._fetch_gitignore(["python"])  # noqa: SLF001
    assert result is None


def test_returns_none_on_oserror(urlopen_raising_oserror: GitignoreBoost) -> None:
    result = urlopen_raising_oserror._fetch_gitignore(["python"])  # noqa: SLF001
    assert result is None


def test_url_contains_all_templates(
    urlopen_capturing_url: CapturingUrlBoost,
) -> None:
    urlopen_capturing_url.boost._fetch_gitignore(["python", "macos", "linux"])  # noqa: SLF001
    called_url = urlopen_capturing_url.mock_request.call_args.args[0]
    assert "python" in called_url
    assert "macos" in called_url
    assert "linux" in called_url


# =============================================================================
# APPEND GITIGNORE
# =============================================================================


def test_creates_new_gitignore_when_absent(mock_repo: RepositoryController, gitignore_boost: GitignoreBoost) -> None:
    gitignore_boost._append_gitignore("*.pyc\n")  # noqa: SLF001
    content = (mock_repo.path / ".gitignore").read_text()
    assert _GITIGNORE_HEADER in content
    assert "*.pyc" in content


def test_appends_to_existing_gitignore(mock_repo: RepositoryController, gitignore_boost: GitignoreBoost) -> None:
    mock_repo.add_file(".gitignore", "*.log\n")
    gitignore_boost._append_gitignore("*.pyc\n")  # noqa: SLF001
    content = (mock_repo.path / ".gitignore").read_text()
    assert "*.log" in content
    assert "*.pyc" in content
    assert _GITIGNORE_HEADER in content


def test_does_not_duplicate_if_header_present(mock_repo: RepositoryController, gitignore_boost: GitignoreBoost) -> None:
    existing = f"*.log\n\n{_GITIGNORE_HEADER}\n*.pyc\n"
    mock_repo.add_file(".gitignore", existing)
    gitignore_boost._append_gitignore("*.new\n")  # noqa: SLF001
    content = (mock_repo.path / ".gitignore").read_text()
    assert content.count(_GITIGNORE_HEADER) == 1
    assert "*.new" not in content


def test_preserves_existing_content(mock_repo: RepositoryController, gitignore_boost: GitignoreBoost) -> None:
    mock_repo.add_file(".gitignore", "# My custom rules\n*.log\nbuild/\n")
    gitignore_boost._append_gitignore("*.pyc\n")  # noqa: SLF001
    content = (mock_repo.path / ".gitignore").read_text()
    assert "# My custom rules" in content
    assert "*.log" in content
    assert "build/" in content


# =============================================================================
# RESET GIT TRACKING
# =============================================================================


def test_calls_rm_cached_then_add(
    gitignore_boost_with_mocked_reset: GitignoreBoostWithMockedReset,
) -> None:
    gitignore_boost_with_mocked_reset.boost._reset_git_tracking()  # noqa: SLF001
    gitignore_boost_with_mocked_reset.mock_reset.assert_called_once()


# =============================================================================
# APPLY
# =============================================================================


@pytest.mark.smoke
def test_apply_writes_gitignore(
    mock_repo: RepositoryController, patched_gitignore_apply: PatchedGitignoreApply
) -> None:
    patched_gitignore_apply.boost.apply()
    assert (mock_repo.path / ".gitignore").exists()


def test_apply_makes_intermediate_commit(patched_gitignore_apply: PatchedGitignoreApply) -> None:
    patched_gitignore_apply.boost.apply()
    messages = [c.args[0] for c in patched_gitignore_apply.mock_commit.call_args_list]
    assert any("✨ Add .gitignore" in m for m in messages)


def test_apply_resets_tracking(patched_gitignore_apply: PatchedGitignoreApply) -> None:
    patched_gitignore_apply.boost.apply()
    patched_gitignore_apply.mock_reset.assert_called_once()


@pytest.mark.smoke
def test_apply_fails_when_fetch_fails(
    mock_repo: RepositoryController,
    patched_gitignore_apply_fetch_fails: PatchedGitignoreApply,
) -> None:
    """When gitignore.io API fails, boost should fail (not skip)."""
    with pytest.raises(RuntimeError, match=r"Could not fetch \.gitignore"):
        patched_gitignore_apply_fetch_fails.boost.apply()
    patched_gitignore_apply_fetch_fails.mock_commit.assert_not_called()
    assert not (mock_repo.path / ".gitignore").exists()


# =============================================================================
# MISC
# =============================================================================


def test_commit_message(gitignore_boost: GitignoreBoost) -> None:
    assert gitignore_boost.commit_message() == "🧹 Remove gitignored files from tracking"


def test_get_name() -> None:
    assert GitignoreBoost.get_name() == "gitignore"
