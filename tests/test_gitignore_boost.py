"""Tests for Gitignore boost implementation."""

import urllib.error
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, call, patch

import pytest

from pimp_my_repo.core.boost.gitignore import (
    _ALWAYS_TEMPLATES,
    _GITIGNORE_HEADER,
    GitignoreBoost,
)

if TYPE_CHECKING:
    from tests.utils.repo_controller import RepositoryController


@pytest.fixture
def gitignore_boost(mock_repo: RepositoryController) -> GitignoreBoost:
    return GitignoreBoost(mock_repo.path)


# =============================================================================
# TEMPLATE DETECTION
# =============================================================================


class TestDetectTemplates:
    def test_always_includes_base_templates(self, gitignore_boost: GitignoreBoost) -> None:
        templates = gitignore_boost._detect_templates()  # noqa: SLF001
        for t in _ALWAYS_TEMPLATES:
            assert t in templates

    def test_detects_python_from_pyproject(
        self, mock_repo: RepositoryController, gitignore_boost: GitignoreBoost
    ) -> None:
        mock_repo.add_file("pyproject.toml", "[project]\nname = 'test'\n")
        assert "python" in gitignore_boost._detect_templates()  # noqa: SLF001

    def test_detects_python_from_setup_py(
        self, mock_repo: RepositoryController, gitignore_boost: GitignoreBoost
    ) -> None:
        mock_repo.add_file("setup.py", "from setuptools import setup")
        assert "python" in gitignore_boost._detect_templates()  # noqa: SLF001

    def test_detects_python_from_requirements_txt(
        self, mock_repo: RepositoryController, gitignore_boost: GitignoreBoost
    ) -> None:
        mock_repo.add_file("requirements.txt", "requests")
        assert "python" in gitignore_boost._detect_templates()  # noqa: SLF001

    def test_detects_node_from_package_json(
        self, mock_repo: RepositoryController, gitignore_boost: GitignoreBoost
    ) -> None:
        mock_repo.add_file("package.json", '{"name": "test"}')
        assert "node" in gitignore_boost._detect_templates()  # noqa: SLF001

    def test_detects_rust_from_cargo_toml(
        self, mock_repo: RepositoryController, gitignore_boost: GitignoreBoost
    ) -> None:
        mock_repo.add_file("Cargo.toml", '[package]\nname = "test"')
        assert "rust" in gitignore_boost._detect_templates()  # noqa: SLF001

    def test_detects_go_from_go_mod(self, mock_repo: RepositoryController, gitignore_boost: GitignoreBoost) -> None:
        mock_repo.add_file("go.mod", "module example.com/mymod\ngo 1.21")
        assert "go" in gitignore_boost._detect_templates()  # noqa: SLF001

    def test_detects_java_maven_from_pom_xml(
        self, mock_repo: RepositoryController, gitignore_boost: GitignoreBoost
    ) -> None:
        mock_repo.add_file("pom.xml", "<project/>")
        templates = gitignore_boost._detect_templates()  # noqa: SLF001
        assert "java" in templates
        assert "maven" in templates

    def test_detects_java_gradle_from_build_gradle(
        self, mock_repo: RepositoryController, gitignore_boost: GitignoreBoost
    ) -> None:
        mock_repo.add_file("build.gradle", "plugins { id 'java' }")
        templates = gitignore_boost._detect_templates()  # noqa: SLF001
        assert "java" in templates
        assert "gradle" in templates

    def test_no_language_detected_for_plain_repo(self, gitignore_boost: GitignoreBoost) -> None:
        # Only README.md exists; no language markers
        templates = gitignore_boost._detect_templates()  # noqa: SLF001
        assert "python" not in templates
        assert "node" not in templates

    def test_detects_multiple_languages(self, mock_repo: RepositoryController, gitignore_boost: GitignoreBoost) -> None:
        mock_repo.add_file("pyproject.toml", "")
        mock_repo.add_file("package.json", "{}")
        templates = gitignore_boost._detect_templates()  # noqa: SLF001
        assert "python" in templates
        assert "node" in templates


# =============================================================================
# FETCH GITIGNORE
# =============================================================================


class TestFetchGitignore:
    def test_returns_content_on_success(self, gitignore_boost: GitignoreBoost) -> None:
        fake_content = "*.pyc\n__pycache__/\n"
        mock_response = MagicMock()
        mock_response.read.return_value = fake_content.encode()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = gitignore_boost._fetch_gitignore(["python"])  # noqa: SLF001
        assert result == fake_content

    def test_returns_none_on_url_error(self, gitignore_boost: GitignoreBoost) -> None:
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("network error")):
            result = gitignore_boost._fetch_gitignore(["python"])  # noqa: SLF001
        assert result is None

    def test_returns_none_on_oserror(self, gitignore_boost: GitignoreBoost) -> None:
        with patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
            result = gitignore_boost._fetch_gitignore(["python"])  # noqa: SLF001
        assert result is None

    def test_url_contains_all_templates(self, gitignore_boost: GitignoreBoost) -> None:
        mock_response = MagicMock()
        mock_response.read.return_value = b""
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response) as mock_open:
            gitignore_boost._fetch_gitignore(["python", "macos", "linux"])  # noqa: SLF001
            called_url = mock_open.call_args[0][0]
        assert "python" in called_url
        assert "macos" in called_url
        assert "linux" in called_url


# =============================================================================
# APPEND GITIGNORE
# =============================================================================


class TestAppendGitignore:
    def test_creates_new_gitignore_when_absent(
        self, mock_repo: RepositoryController, gitignore_boost: GitignoreBoost
    ) -> None:
        gitignore_boost._append_gitignore("*.pyc\n")  # noqa: SLF001
        content = (mock_repo.path / ".gitignore").read_text()
        assert _GITIGNORE_HEADER in content
        assert "*.pyc" in content

    def test_appends_to_existing_gitignore(
        self, mock_repo: RepositoryController, gitignore_boost: GitignoreBoost
    ) -> None:
        mock_repo.add_file(".gitignore", "*.log\n")
        gitignore_boost._append_gitignore("*.pyc\n")  # noqa: SLF001
        content = (mock_repo.path / ".gitignore").read_text()
        assert "*.log" in content
        assert "*.pyc" in content
        assert _GITIGNORE_HEADER in content

    def test_does_not_duplicate_if_header_present(
        self, mock_repo: RepositoryController, gitignore_boost: GitignoreBoost
    ) -> None:
        existing = f"*.log\n\n{_GITIGNORE_HEADER}\n*.pyc\n"
        mock_repo.add_file(".gitignore", existing)
        gitignore_boost._append_gitignore("*.new\n")  # noqa: SLF001
        content = (mock_repo.path / ".gitignore").read_text()
        assert content.count(_GITIGNORE_HEADER) == 1
        assert "*.new" not in content

    def test_preserves_existing_content(self, mock_repo: RepositoryController, gitignore_boost: GitignoreBoost) -> None:
        mock_repo.add_file(".gitignore", "# My custom rules\n*.log\nbuild/\n")
        gitignore_boost._append_gitignore("*.pyc\n")  # noqa: SLF001
        content = (mock_repo.path / ".gitignore").read_text()
        assert "# My custom rules" in content
        assert "*.log" in content
        assert "build/" in content


# =============================================================================
# RESET GIT TRACKING
# =============================================================================


class TestResetGitTracking:
    def test_calls_rm_cached_then_add(self, gitignore_boost: GitignoreBoost) -> None:
        with patch.object(gitignore_boost, "_run_git") as mock_git:
            gitignore_boost._reset_git_tracking()  # noqa: SLF001
        assert mock_git.call_args_list == [
            call("rm", "-r", "--cached", "."),
            call("add", "-A"),
        ]


# =============================================================================
# APPLY
# =============================================================================


class TestApply:
    _FAKE_GITIGNORE = "*.pyc\n__pycache__/\n.venv/\n"

    def test_apply_writes_gitignore(self, mock_repo: RepositoryController, gitignore_boost: GitignoreBoost) -> None:
        with (
            patch.object(gitignore_boost, "_fetch_gitignore", return_value=self._FAKE_GITIGNORE),
            patch.object(gitignore_boost, "_run_git"),
        ):
            gitignore_boost.apply()
        assert (mock_repo.path / ".gitignore").exists()

    def test_apply_makes_intermediate_commit(self, gitignore_boost: GitignoreBoost) -> None:
        with (
            patch.object(gitignore_boost, "_fetch_gitignore", return_value=self._FAKE_GITIGNORE),
            patch.object(gitignore_boost, "_run_git") as mock_git,
        ):
            gitignore_boost.apply()
        commit_calls = [c for c in mock_git.call_args_list if "commit" in c.args]
        assert len(commit_calls) == 1
        assert "✨ Add .gitignore" in commit_calls[0].args

    def test_apply_resets_tracking(self, gitignore_boost: GitignoreBoost) -> None:
        with (
            patch.object(gitignore_boost, "_fetch_gitignore", return_value=self._FAKE_GITIGNORE),
            patch.object(gitignore_boost, "_run_git") as mock_git,
        ):
            gitignore_boost.apply()
        all_args = [c.args for c in mock_git.call_args_list]
        assert ("rm", "-r", "--cached", ".") in all_args
        assert ("add", "-A") in all_args

    def test_apply_skips_when_fetch_fails(
        self, mock_repo: RepositoryController, gitignore_boost: GitignoreBoost
    ) -> None:
        with (
            patch.object(gitignore_boost, "_fetch_gitignore", return_value=None),
            patch.object(gitignore_boost, "_run_git") as mock_git,
        ):
            gitignore_boost.apply()
        mock_git.assert_not_called()
        assert not (mock_repo.path / ".gitignore").exists()


# =============================================================================
# VERIFY
# =============================================================================


# =============================================================================
# MISC
# =============================================================================


def test_commit_message(gitignore_boost: GitignoreBoost) -> None:
    assert gitignore_boost.commit_message() == "🧹 Remove gitignored files from tracking"


def test_get_name() -> None:
    assert GitignoreBoost.get_name() == "gitignore"
