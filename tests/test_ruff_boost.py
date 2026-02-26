"""Tests for Ruff boost implementation."""

from dataclasses import dataclass
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from pimp_my_repo.core.boosts import BoostSkippedError
from pimp_my_repo.core.boosts.ruff import _MAX_RUFF_ITERATIONS, RuffBoost, ViolationLocation

if TYPE_CHECKING:
    from collections.abc import Generator

    from pimp_my_repo.core.tools.boost_tools import BoostTools
    from tests.conftest import SubprocessResultFactory
    from tests.repo_controller import RepositoryController


@pytest.fixture
def ruff_boost(boost_tools: BoostTools) -> RuffBoost:
    return RuffBoost(boost_tools)


@pytest.fixture
def ruff_boost_with_pyproject(boost_tools: BoostTools, repo_controller: RepositoryController) -> RuffBoost:
    repo_controller.add_file("pyproject.toml", "[project]\nname = 'test'\nversion = '0.1.0'\n")
    return RuffBoost(boost_tools)


@dataclass
class PatchedRuffApply:
    """Pre-patched RuffBoost with all subprocess mocks wired for apply()."""

    boost: RuffBoost
    mock_uv: MagicMock
    mock_git: MagicMock
    mock_format: MagicMock
    mock_check: MagicMock


@pytest.fixture
def patched_ruff_apply(
    ruff_boost_with_pyproject: RuffBoost,
    ok_result: SubprocessResultFactory,
) -> Generator[PatchedRuffApply]:
    """Yield a RuffBoost with all subprocess calls pre-mocked to succeed."""
    with (
        patch.object(ruff_boost_with_pyproject, "_run_uv", return_value=ok_result()) as mock_uv,
        patch.object(ruff_boost_with_pyproject, "_run_git") as mock_git,
        patch.object(ruff_boost_with_pyproject, "_run_ruff_format", return_value=ok_result()) as mock_fmt,
        patch.object(ruff_boost_with_pyproject, "_run_ruff_check", return_value=ok_result()) as mock_check,
    ):
        yield PatchedRuffApply(
            boost=ruff_boost_with_pyproject,
            mock_uv=mock_uv,
            mock_git=mock_git,
            mock_format=mock_fmt,
            mock_check=mock_check,
        )


# =============================================================================
# PRECONDITIONS
# =============================================================================


def test_raises_skip_when_uv_nonzero(
    ruff_boost_with_pyproject: RuffBoost, fail_result: SubprocessResultFactory
) -> None:
    with (
        patch("pimp_my_repo.core.boosts.add_package.run_uv", return_value=fail_result()),
        pytest.raises(BoostSkippedError, match="uv is not available"),
    ):
        ruff_boost_with_pyproject.apply()


def test_raises_skip_when_uv_raises_file_not_found(ruff_boost_with_pyproject: RuffBoost) -> None:
    with (
        patch("pimp_my_repo.core.boosts.add_package.run_uv", side_effect=FileNotFoundError),
        pytest.raises(BoostSkippedError, match="uv is not installed"),
    ):
        ruff_boost_with_pyproject.apply()


def test_raises_skip_when_uv_raises_oserror(ruff_boost_with_pyproject: RuffBoost) -> None:
    with (
        patch("pimp_my_repo.core.boosts.add_package.run_uv", side_effect=OSError),
        pytest.raises(BoostSkippedError, match="uv is not installed"),
    ):
        ruff_boost_with_pyproject.apply()


def test_raises_skip_when_no_pyproject(ruff_boost: RuffBoost, ok_result: SubprocessResultFactory) -> None:
    with (
        patch.object(ruff_boost, "_run_uv", return_value=ok_result()),
        pytest.raises(BoostSkippedError, match=r"No pyproject\.toml found"),
    ):
        ruff_boost.apply()


# =============================================================================
# PARSE VIOLATIONS
# =============================================================================


def test_parses_single_violation(ruff_boost: RuffBoost) -> None:
    output = "src/foo.py:10:5: E501 Line too long (120 > 79 characters)"
    assert ruff_boost._parse_violations(output) == {ViolationLocation("src/foo.py", 10): {"E501"}}  # noqa: SLF001


def test_parses_violations_on_different_lines(ruff_boost: RuffBoost) -> None:
    output = "src/foo.py:10:5: E501 Line too long\nsrc/foo.py:20:1: F401 `os` imported but unused\n"
    result = ruff_boost._parse_violations(output)  # noqa: SLF001
    assert result == {
        ViolationLocation("src/foo.py", 10): {"E501"},
        ViolationLocation("src/foo.py", 20): {"F401"},
    }


def test_accumulates_multiple_codes_on_same_line(ruff_boost: RuffBoost) -> None:
    output = "src/foo.py:5:1: E501 Line too long\nsrc/foo.py:5:1: F401 Unused import\n"
    result = ruff_boost._parse_violations(output)  # noqa: SLF001
    assert result == {ViolationLocation("src/foo.py", 5): {"E501", "F401"}}


def test_parses_violations_across_multiple_files(ruff_boost: RuffBoost) -> None:
    output = "src/foo.py:1:1: F401 Unused import\nsrc/bar.py:2:1: E501 Line too long\n"
    result = ruff_boost._parse_violations(output)  # noqa: SLF001
    assert ViolationLocation("src/foo.py", 1) in result
    assert ViolationLocation("src/bar.py", 2) in result


def test_ignores_non_violation_lines(ruff_boost: RuffBoost) -> None:
    output = "src/foo.py:10:5: E501 Line too long\nFound 1 error.\nNo fixes available.\n"
    result = ruff_boost._parse_violations(output)  # noqa: SLF001
    assert len(result) == 1


def test_empty_output(ruff_boost: RuffBoost) -> None:
    assert ruff_boost._parse_violations("") == {}  # noqa: SLF001


def test_all_checks_passed_output(ruff_boost: RuffBoost) -> None:
    assert ruff_boost._parse_violations("All checks passed!\n") == {}  # noqa: SLF001


# =============================================================================
# APPLY NOQA
# =============================================================================


def test_adds_noqa_comment_to_clean_line(mock_repo: RepositoryController, ruff_boost: RuffBoost) -> None:
    mock_repo.add_file("src/foo.py", "import os\n")
    ruff_boost._apply_noqa({ViolationLocation("src/foo.py", 1): {"F401"}})  # noqa: SLF001
    assert "# noqa: F401" in (mock_repo.path / "src/foo.py").read_text()


def test_merges_new_code_with_existing_noqa(mock_repo: RepositoryController, ruff_boost: RuffBoost) -> None:
    mock_repo.add_file("src/foo.py", "import os  # noqa: F401\n")
    ruff_boost._apply_noqa({ViolationLocation("src/foo.py", 1): {"E501"}})  # noqa: SLF001
    content = (mock_repo.path / "src/foo.py").read_text()
    assert "F401" in content
    assert "E501" in content
    assert content.count("# noqa") == 1


def test_merges_multiple_codes_on_same_line(mock_repo: RepositoryController, ruff_boost: RuffBoost) -> None:
    mock_repo.add_file("src/foo.py", "import os\n")
    ruff_boost._apply_noqa({ViolationLocation("src/foo.py", 1): {"F401", "E501"}})  # noqa: SLF001
    content = (mock_repo.path / "src/foo.py").read_text()
    assert "# noqa: " in content
    assert "F401" in content
    assert "E501" in content


def test_handles_multiple_lines_in_same_file(mock_repo: RepositoryController, ruff_boost: RuffBoost) -> None:
    mock_repo.add_file("src/foo.py", "import os\nimport sys\n")
    ruff_boost._apply_noqa(  # noqa: SLF001
        {
            ViolationLocation("src/foo.py", 1): {"F401"},
            ViolationLocation("src/foo.py", 2): {"F401"},
        }
    )
    lines = (mock_repo.path / "src/foo.py").read_text().splitlines()
    assert "# noqa: F401" in lines[0]
    assert "# noqa: F401" in lines[1]


def test_handles_multiple_files(mock_repo: RepositoryController, ruff_boost: RuffBoost) -> None:
    mock_repo.add_file("src/foo.py", "import os\n")
    mock_repo.add_file("src/bar.py", "import sys\n")
    ruff_boost._apply_noqa(  # noqa: SLF001
        {
            ViolationLocation("src/foo.py", 1): {"F401"},
            ViolationLocation("src/bar.py", 1): {"F401"},
        }
    )
    assert "# noqa" in (mock_repo.path / "src/foo.py").read_text()
    assert "# noqa" in (mock_repo.path / "src/bar.py").read_text()


def test_skips_missing_file_without_raising(ruff_boost: RuffBoost) -> None:
    ruff_boost._apply_noqa({ViolationLocation("nonexistent.py", 1): {"F401"}})  # noqa: SLF001


def test_noqa_codes_sorted_alphabetically(mock_repo: RepositoryController, ruff_boost: RuffBoost) -> None:
    mock_repo.add_file("src/foo.py", "import os\n")
    ruff_boost._apply_noqa({ViolationLocation("src/foo.py", 1): {"F401", "E501", "ANN201"}})  # noqa: SLF001
    content = (mock_repo.path / "src/foo.py").read_text()
    ann_pos = content.index("ANN201")
    e501_pos = content.index("E501")
    f401_pos = content.index("F401")
    assert ann_pos < e501_pos < f401_pos


def test_noqa_preserves_existing_line_content(mock_repo: RepositoryController, ruff_boost: RuffBoost) -> None:
    mock_repo.add_file("src/foo.py", "result = some_func(arg1, arg2)\n")
    ruff_boost._apply_noqa({ViolationLocation("src/foo.py", 1): {"E501"}})  # noqa: SLF001
    content = (mock_repo.path / "src/foo.py").read_text()
    assert "result = some_func(arg1, arg2)" in content
    assert "# noqa: E501" in content


# =============================================================================
# ENSURE RUFF CONFIG
# =============================================================================


def test_adds_ruff_section_when_missing(mock_repo: RepositoryController, ruff_boost: RuffBoost) -> None:
    mock_repo.add_file("pyproject.toml", "[project]\nname = 'test'\n")
    data = ruff_boost._read_pyproject()  # noqa: SLF001
    data = ruff_boost._ensure_ruff_config(data)  # noqa: SLF001
    ruff_boost._write_pyproject(data)  # noqa: SLF001
    content = (mock_repo.path / "pyproject.toml").read_text()
    assert "[tool.ruff" in content
    assert 'select = ["ALL"]' in content


def test_ruff_config_sets_line_length(mock_repo: RepositoryController, ruff_boost: RuffBoost) -> None:
    mock_repo.add_file("pyproject.toml", "[project]\nname = 'test'\n")
    data = ruff_boost._read_pyproject()  # noqa: SLF001
    data = ruff_boost._ensure_ruff_config(data)  # noqa: SLF001
    ruff_boost._write_pyproject(data)  # noqa: SLF001
    content = (mock_repo.path / "pyproject.toml").read_text()
    assert "line-length = 120" in content


def test_ruff_config_preserves_existing_content(mock_repo: RepositoryController, ruff_boost: RuffBoost) -> None:
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


def test_apply_calls_uv_add_ruff(patched_ruff_apply: PatchedRuffApply) -> None:
    with patch("pimp_my_repo.core.boosts.add_package.add_package_with_uv") as mock_add:
        patched_ruff_apply.boost.apply()
        mock_add.assert_called_once_with(patched_ruff_apply.boost.tools.repo_controller.path, "ruff", group="lint")


def test_apply_writes_ruff_config_to_pyproject(
    mock_repo: RepositoryController, patched_ruff_apply: PatchedRuffApply
) -> None:
    patched_ruff_apply.boost.apply()
    content = (mock_repo.path / "pyproject.toml").read_text()
    assert 'select = ["ALL"]' in content


def test_apply_makes_two_intermediate_commits(patched_ruff_apply: PatchedRuffApply) -> None:
    patched_ruff_apply.boost.apply()
    commit_calls = [c for c in patched_ruff_apply.mock_git.call_args_list if "commit" in c.args]
    messages = [c.args[c.args.index("-m") + 1] for c in commit_calls]
    assert any("Configure ruff" in m for m in messages)
    assert any("Auto-format" in m for m in messages)


def test_apply_runs_format(patched_ruff_apply: PatchedRuffApply) -> None:
    patched_ruff_apply.boost.apply()
    patched_ruff_apply.mock_format.assert_called_once()


def test_apply_stops_when_check_passes(patched_ruff_apply: PatchedRuffApply) -> None:
    patched_ruff_apply.boost.apply()
    patched_ruff_apply.mock_check.assert_called_once()


def test_apply_inserts_noqa_on_violation(
    mock_repo: RepositoryController,
    patched_ruff_apply: PatchedRuffApply,
    fail_result: SubprocessResultFactory,
    ok_result: SubprocessResultFactory,
) -> None:
    mock_repo.add_file("src/foo.py", "import os\n")
    patched_ruff_apply.mock_check.side_effect = [
        fail_result("src/foo.py:1:1: F401 `os` imported but unused"),
        ok_result(),
    ]
    patched_ruff_apply.boost.apply()
    assert "# noqa: F401" in (mock_repo.path / "src/foo.py").read_text()


def test_apply_iterates_until_check_passes(
    mock_repo: RepositoryController,
    patched_ruff_apply: PatchedRuffApply,
    fail_result: SubprocessResultFactory,
    ok_result: SubprocessResultFactory,
) -> None:
    mock_repo.add_file("src/foo.py", "import os\n")
    patched_ruff_apply.mock_check.side_effect = [
        fail_result("src/foo.py:1:1: F401 Unused import"),
        fail_result("src/foo.py:1:1: E501 Line too long"),
        ok_result(),
    ]
    patched_ruff_apply.boost.apply()
    assert patched_ruff_apply.mock_check.call_count == 3  # noqa: PLR2004


def test_apply_stops_after_max_iterations(
    mock_repo: RepositoryController,
    patched_ruff_apply: PatchedRuffApply,
    fail_result: SubprocessResultFactory,
) -> None:
    mock_repo.add_file("src/foo.py", "import os\n")
    patched_ruff_apply.mock_check.return_value = fail_result("src/foo.py:1:1: F401 Persistent violation")
    patched_ruff_apply.boost.apply()
    assert patched_ruff_apply.mock_check.call_count == _MAX_RUFF_ITERATIONS


def test_apply_stops_early_when_no_parseable_violations(
    patched_ruff_apply: PatchedRuffApply,
    fail_result: SubprocessResultFactory,
) -> None:
    patched_ruff_apply.mock_check.return_value = fail_result("some unparseable output\n")
    patched_ruff_apply.boost.apply()
    patched_ruff_apply.mock_check.assert_called_once()


# =============================================================================
# MISC
# =============================================================================


def test_commit_message(ruff_boost: RuffBoost) -> None:
    assert ruff_boost.commit_message() == "✅ Silence ruff violations"


def test_get_name() -> None:
    assert RuffBoost.get_name() == "ruff"
