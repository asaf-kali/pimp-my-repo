"""Tests for Ruff boost implementation."""

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from pimp_my_repo.core.boost.base import BoostSkippedError
from pimp_my_repo.core.boost.ruff import _MAX_RUFF_ITERATIONS, RuffBoost

if TYPE_CHECKING:
    from tests.utils.repo_controller import RepositoryController


@pytest.fixture
def ruff_boost(mock_repo: RepositoryController) -> RuffBoost:
    return RuffBoost(mock_repo.path)


@pytest.fixture
def ruff_boost_with_pyproject(mock_repo: RepositoryController) -> RuffBoost:
    mock_repo.add_file("pyproject.toml", "[project]\nname = 'test'\nversion = '0.1.0'\n")
    return RuffBoost(mock_repo.path)


def _ok(output: str = "") -> MagicMock:
    r = MagicMock()
    r.returncode = 0
    r.stdout = output
    r.stderr = ""
    return r


def _fail(output: str = "") -> MagicMock:
    r = MagicMock()
    r.returncode = 1
    r.stdout = output
    r.stderr = ""
    return r


# =============================================================================
# PRECONDITIONS
# =============================================================================


class TestApplySkipConditions:
    def test_raises_skip_when_uv_nonzero(self, ruff_boost_with_pyproject: RuffBoost) -> None:
        with (
            patch.object(ruff_boost_with_pyproject, "_run_uv", return_value=_fail()),
            pytest.raises(BoostSkippedError, match="uv is not available"),
        ):
            ruff_boost_with_pyproject.apply()

    def test_raises_skip_when_uv_raises_file_not_found(self, ruff_boost_with_pyproject: RuffBoost) -> None:
        with (
            patch.object(ruff_boost_with_pyproject, "_run_uv", side_effect=FileNotFoundError),
            pytest.raises(BoostSkippedError, match="uv is not installed"),
        ):
            ruff_boost_with_pyproject.apply()

    def test_raises_skip_when_uv_raises_oserror(self, ruff_boost_with_pyproject: RuffBoost) -> None:
        with (
            patch.object(ruff_boost_with_pyproject, "_run_uv", side_effect=OSError),
            pytest.raises(BoostSkippedError, match="uv is not installed"),
        ):
            ruff_boost_with_pyproject.apply()

    def test_raises_skip_when_no_pyproject(self, ruff_boost: RuffBoost) -> None:
        with (
            patch.object(ruff_boost, "_run_uv", return_value=_ok()),
            pytest.raises(BoostSkippedError, match=r"No pyproject\.toml found"),
        ):
            ruff_boost.apply()


# =============================================================================
# PARSE VIOLATIONS
# =============================================================================


class TestParseViolations:
    def test_parses_single_violation(self, ruff_boost: RuffBoost) -> None:
        output = "src/foo.py:10:5: E501 Line too long (120 > 79 characters)"
        assert ruff_boost._parse_violations(output) == {("src/foo.py", 10): {"E501"}}  # noqa: SLF001

    def test_parses_violations_on_different_lines(self, ruff_boost: RuffBoost) -> None:
        output = "src/foo.py:10:5: E501 Line too long\nsrc/foo.py:20:1: F401 `os` imported but unused\n"
        result = ruff_boost._parse_violations(output)  # noqa: SLF001
        assert result == {
            ("src/foo.py", 10): {"E501"},
            ("src/foo.py", 20): {"F401"},
        }

    def test_accumulates_multiple_codes_on_same_line(self, ruff_boost: RuffBoost) -> None:
        output = "src/foo.py:5:1: E501 Line too long\nsrc/foo.py:5:1: F401 Unused import\n"
        result = ruff_boost._parse_violations(output)  # noqa: SLF001
        assert result == {("src/foo.py", 5): {"E501", "F401"}}

    def test_parses_violations_across_multiple_files(self, ruff_boost: RuffBoost) -> None:
        output = "src/foo.py:1:1: F401 Unused import\nsrc/bar.py:2:1: E501 Line too long\n"
        result = ruff_boost._parse_violations(output)  # noqa: SLF001
        assert ("src/foo.py", 1) in result
        assert ("src/bar.py", 2) in result

    def test_ignores_non_violation_lines(self, ruff_boost: RuffBoost) -> None:
        output = "src/foo.py:10:5: E501 Line too long\nFound 1 error.\nNo fixes available.\n"
        result = ruff_boost._parse_violations(output)  # noqa: SLF001
        assert len(result) == 1

    def test_empty_output(self, ruff_boost: RuffBoost) -> None:
        assert ruff_boost._parse_violations("") == {}  # noqa: SLF001

    def test_all_checks_passed_output(self, ruff_boost: RuffBoost) -> None:
        assert ruff_boost._parse_violations("All checks passed!\n") == {}  # noqa: SLF001


# =============================================================================
# APPLY NOQA
# =============================================================================


class TestApplyNoqa:
    def test_adds_noqa_comment_to_clean_line(self, mock_repo: RepositoryController, ruff_boost: RuffBoost) -> None:
        mock_repo.add_file("src/foo.py", "import os\n")
        ruff_boost._apply_noqa({("src/foo.py", 1): {"F401"}})  # noqa: SLF001
        assert "# noqa: F401" in (mock_repo.path / "src/foo.py").read_text()

    def test_merges_new_code_with_existing_noqa(self, mock_repo: RepositoryController, ruff_boost: RuffBoost) -> None:
        mock_repo.add_file("src/foo.py", "import os  # noqa: F401\n")
        ruff_boost._apply_noqa({("src/foo.py", 1): {"E501"}})  # noqa: SLF001
        content = (mock_repo.path / "src/foo.py").read_text()
        assert "F401" in content
        assert "E501" in content
        assert content.count("# noqa") == 1

    def test_merges_multiple_codes_on_same_line(self, mock_repo: RepositoryController, ruff_boost: RuffBoost) -> None:
        mock_repo.add_file("src/foo.py", "import os\n")
        ruff_boost._apply_noqa({("src/foo.py", 1): {"F401", "E501"}})  # noqa: SLF001
        content = (mock_repo.path / "src/foo.py").read_text()
        assert "# noqa: " in content
        assert "F401" in content
        assert "E501" in content

    def test_handles_multiple_lines_in_same_file(self, mock_repo: RepositoryController, ruff_boost: RuffBoost) -> None:
        mock_repo.add_file("src/foo.py", "import os\nimport sys\n")
        ruff_boost._apply_noqa(  # noqa: SLF001
            {
                ("src/foo.py", 1): {"F401"},
                ("src/foo.py", 2): {"F401"},
            }
        )
        lines = (mock_repo.path / "src/foo.py").read_text().splitlines()
        assert "# noqa: F401" in lines[0]
        assert "# noqa: F401" in lines[1]

    def test_handles_multiple_files(self, mock_repo: RepositoryController, ruff_boost: RuffBoost) -> None:
        mock_repo.add_file("src/foo.py", "import os\n")
        mock_repo.add_file("src/bar.py", "import sys\n")
        ruff_boost._apply_noqa(  # noqa: SLF001
            {
                ("src/foo.py", 1): {"F401"},
                ("src/bar.py", 1): {"F401"},
            }
        )
        assert "# noqa" in (mock_repo.path / "src/foo.py").read_text()
        assert "# noqa" in (mock_repo.path / "src/bar.py").read_text()

    def test_skips_missing_file_without_raising(self, ruff_boost: RuffBoost) -> None:
        ruff_boost._apply_noqa({("nonexistent.py", 1): {"F401"}})  # noqa: SLF001

    def test_codes_sorted_alphabetically(self, mock_repo: RepositoryController, ruff_boost: RuffBoost) -> None:
        mock_repo.add_file("src/foo.py", "import os\n")
        ruff_boost._apply_noqa({("src/foo.py", 1): {"F401", "E501", "ANN201"}})  # noqa: SLF001
        content = (mock_repo.path / "src/foo.py").read_text()
        ann_pos = content.index("ANN201")
        e501_pos = content.index("E501")
        f401_pos = content.index("F401")
        assert ann_pos < e501_pos < f401_pos

    def test_preserves_existing_line_content(self, mock_repo: RepositoryController, ruff_boost: RuffBoost) -> None:
        mock_repo.add_file("src/foo.py", "result = some_func(arg1, arg2)\n")
        ruff_boost._apply_noqa({("src/foo.py", 1): {"E501"}})  # noqa: SLF001
        content = (mock_repo.path / "src/foo.py").read_text()
        assert "result = some_func(arg1, arg2)" in content
        assert "# noqa: E501" in content


# =============================================================================
# ENSURE RUFF CONFIG
# =============================================================================


class TestEnsureRuffConfig:
    def test_adds_ruff_section_when_missing(self, mock_repo: RepositoryController, ruff_boost: RuffBoost) -> None:
        mock_repo.add_file("pyproject.toml", "[project]\nname = 'test'\n")
        data = ruff_boost._read_pyproject()  # noqa: SLF001
        data = ruff_boost._ensure_ruff_config(data)  # noqa: SLF001
        ruff_boost._write_pyproject(data)  # noqa: SLF001
        content = (mock_repo.path / "pyproject.toml").read_text()
        assert "[tool.ruff" in content
        assert 'select = ["ALL"]' in content

    def test_sets_line_length(self, mock_repo: RepositoryController, ruff_boost: RuffBoost) -> None:
        mock_repo.add_file("pyproject.toml", "[project]\nname = 'test'\n")
        data = ruff_boost._read_pyproject()  # noqa: SLF001
        data = ruff_boost._ensure_ruff_config(data)  # noqa: SLF001
        ruff_boost._write_pyproject(data)  # noqa: SLF001
        content = (mock_repo.path / "pyproject.toml").read_text()
        assert "line-length = 120" in content

    def test_preserves_existing_content(self, mock_repo: RepositoryController, ruff_boost: RuffBoost) -> None:
        mock_repo.add_file("pyproject.toml", "[project]\nname = 'test'\n\n[tool.mypy]\nstrict = true\n")
        data = ruff_boost._read_pyproject()  # noqa: SLF001
        data = ruff_boost._ensure_ruff_config(data)  # noqa: SLF001
        ruff_boost._write_pyproject(data)  # noqa: SLF001
        content = (mock_repo.path / "pyproject.toml").read_text()
        assert "[tool.mypy]" in content
        assert "strict = true" in content


# =============================================================================
# APPLY
# =============================================================================


class TestApply:
    def test_apply_calls_uv_add_ruff(self, ruff_boost_with_pyproject: RuffBoost) -> None:
        with (
            patch.object(ruff_boost_with_pyproject, "_run_uv", return_value=_ok()) as mock_uv,
            patch.object(ruff_boost_with_pyproject, "_run_git"),
            patch.object(ruff_boost_with_pyproject, "_run_ruff_format", return_value=_ok()),
            patch.object(ruff_boost_with_pyproject, "_run_ruff_check", return_value=_ok()),
        ):
            ruff_boost_with_pyproject.apply()
            mock_uv.assert_any_call("add", "--group", "lint", "ruff")

    def test_apply_writes_ruff_config_to_pyproject(
        self, mock_repo: RepositoryController, ruff_boost_with_pyproject: RuffBoost
    ) -> None:
        with (
            patch.object(ruff_boost_with_pyproject, "_run_uv", return_value=_ok()),
            patch.object(ruff_boost_with_pyproject, "_run_git"),
            patch.object(ruff_boost_with_pyproject, "_run_ruff_format", return_value=_ok()),
            patch.object(ruff_boost_with_pyproject, "_run_ruff_check", return_value=_ok()),
        ):
            ruff_boost_with_pyproject.apply()
        content = (mock_repo.path / "pyproject.toml").read_text()
        assert 'select = ["ALL"]' in content

    def test_apply_makes_two_intermediate_commits(self, ruff_boost_with_pyproject: RuffBoost) -> None:
        with (
            patch.object(ruff_boost_with_pyproject, "_run_uv", return_value=_ok()),
            patch.object(ruff_boost_with_pyproject, "_run_git") as mock_git,
            patch.object(ruff_boost_with_pyproject, "_run_ruff_format", return_value=_ok()),
            patch.object(ruff_boost_with_pyproject, "_run_ruff_check", return_value=_ok()),
        ):
            ruff_boost_with_pyproject.apply()
        commit_calls = [c for c in mock_git.call_args_list if "commit" in c.args]
        messages = [c.args[c.args.index("-m") + 1] for c in commit_calls]
        assert any("Configure ruff" in m for m in messages)
        assert any("Auto-format" in m for m in messages)

    def test_apply_runs_format(self, ruff_boost_with_pyproject: RuffBoost) -> None:
        with (
            patch.object(ruff_boost_with_pyproject, "_run_uv", return_value=_ok()),
            patch.object(ruff_boost_with_pyproject, "_run_git"),
            patch.object(ruff_boost_with_pyproject, "_run_ruff_format", return_value=_ok()) as mock_fmt,
            patch.object(ruff_boost_with_pyproject, "_run_ruff_check", return_value=_ok()),
        ):
            ruff_boost_with_pyproject.apply()
            mock_fmt.assert_called_once()

    def test_apply_stops_when_check_passes(self, ruff_boost_with_pyproject: RuffBoost) -> None:
        with (
            patch.object(ruff_boost_with_pyproject, "_run_uv", return_value=_ok()),
            patch.object(ruff_boost_with_pyproject, "_run_git"),
            patch.object(ruff_boost_with_pyproject, "_run_ruff_format", return_value=_ok()),
            patch.object(ruff_boost_with_pyproject, "_run_ruff_check", return_value=_ok()) as mock_check,
        ):
            ruff_boost_with_pyproject.apply()
            mock_check.assert_called_once()

    def test_apply_inserts_noqa_on_violation(
        self, mock_repo: RepositoryController, ruff_boost_with_pyproject: RuffBoost
    ) -> None:
        mock_repo.add_file("src/foo.py", "import os\n")
        fail = _fail("src/foo.py:1:1: F401 `os` imported but unused")
        with (
            patch.object(ruff_boost_with_pyproject, "_run_uv", return_value=_ok()),
            patch.object(ruff_boost_with_pyproject, "_run_git"),
            patch.object(ruff_boost_with_pyproject, "_run_ruff_format", return_value=_ok()),
            patch.object(ruff_boost_with_pyproject, "_run_ruff_check", side_effect=[fail, _ok()]),
        ):
            ruff_boost_with_pyproject.apply()
        assert "# noqa: F401" in (mock_repo.path / "src/foo.py").read_text()

    def test_apply_iterates_until_check_passes(
        self, mock_repo: RepositoryController, ruff_boost_with_pyproject: RuffBoost
    ) -> None:
        mock_repo.add_file("src/foo.py", "import os\n")
        fail1 = _fail("src/foo.py:1:1: F401 Unused import")
        fail2 = _fail("src/foo.py:1:1: E501 Line too long")
        with (
            patch.object(ruff_boost_with_pyproject, "_run_uv", return_value=_ok()),
            patch.object(ruff_boost_with_pyproject, "_run_git"),
            patch.object(ruff_boost_with_pyproject, "_run_ruff_format", return_value=_ok()),
            patch.object(ruff_boost_with_pyproject, "_run_ruff_check", side_effect=[fail1, fail2, _ok()]) as mock_check,
        ):
            ruff_boost_with_pyproject.apply()
            assert mock_check.call_count == 3  # noqa: PLR2004

    def test_apply_stops_after_max_iterations(
        self, mock_repo: RepositoryController, ruff_boost_with_pyproject: RuffBoost
    ) -> None:
        mock_repo.add_file("src/foo.py", "import os\n")
        fail = _fail("src/foo.py:1:1: F401 Persistent violation")
        with (
            patch.object(ruff_boost_with_pyproject, "_run_uv", return_value=_ok()),
            patch.object(ruff_boost_with_pyproject, "_run_git"),
            patch.object(ruff_boost_with_pyproject, "_run_ruff_format", return_value=_ok()),
            patch.object(ruff_boost_with_pyproject, "_run_ruff_check", return_value=fail) as mock_check,
        ):
            ruff_boost_with_pyproject.apply()
            assert mock_check.call_count == _MAX_RUFF_ITERATIONS

    def test_apply_stops_early_when_no_parseable_violations(self, ruff_boost_with_pyproject: RuffBoost) -> None:
        fail = _fail("some unparseable output\n")
        with (
            patch.object(ruff_boost_with_pyproject, "_run_uv", return_value=_ok()),
            patch.object(ruff_boost_with_pyproject, "_run_git"),
            patch.object(ruff_boost_with_pyproject, "_run_ruff_format", return_value=_ok()),
            patch.object(ruff_boost_with_pyproject, "_run_ruff_check", return_value=fail) as mock_check,
        ):
            ruff_boost_with_pyproject.apply()
            mock_check.assert_called_once()


# =============================================================================
# VERIFY
# =============================================================================


# =============================================================================
# MISC
# =============================================================================


def test_commit_message(ruff_boost: RuffBoost) -> None:
    assert ruff_boost.commit_message() == "✅ Silence ruff violations"


def test_get_name() -> None:
    assert RuffBoost.get_name() == "ruff"
