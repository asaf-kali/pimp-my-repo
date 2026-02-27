"""Tests for Mypy boost implementation."""

from dataclasses import dataclass
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from pimp_my_repo.core.boosts.base import BoostSkippedError
from pimp_my_repo.core.boosts.mypy import _MAX_MYPY_ITERATIONS, MypyBoost, ViolationLocation

if TYPE_CHECKING:
    from collections.abc import Generator

    from pimp_my_repo.core.tools.boost_tools import BoostTools
    from tests.conftest import SubprocessResultFactory
    from tests.repo_controller import RepositoryController

_vl = ViolationLocation


@pytest.fixture
def mypy_boost(boost_tools: BoostTools) -> MypyBoost:
    """Create a MypyBoost instance without pyproject.toml."""
    return MypyBoost(boost_tools)


@pytest.fixture
def mypy_boost_with_pyproject(repo_controller: RepositoryController, boost_tools: BoostTools) -> MypyBoost:
    """Create a MypyBoost instance with a minimal pyproject.toml."""
    repo_controller.add_file("pyproject.toml", "[project]\nname = 'test'\nversion = '0.1.0'\n")
    return MypyBoost(boost_tools)


@dataclass
class PatchedMypyApply:
    """Pre-patched MypyBoost with all subprocess mocks wired for apply()."""

    boost: MypyBoost
    mock_uv: MagicMock
    mock_git: MagicMock
    mock_mypy: MagicMock


@pytest.fixture
def patched_mypy_apply(
    mypy_boost_with_pyproject: MypyBoost,
    ok_result: SubprocessResultFactory,
) -> Generator[PatchedMypyApply]:
    """Yield a MypyBoost with all subprocess calls pre-mocked to succeed."""
    with (
        patch.object(mypy_boost_with_pyproject, "_run_uv", return_value=ok_result()) as mock_uv,
        patch.object(mypy_boost_with_pyproject, "_run_git") as mock_git,
        patch.object(mypy_boost_with_pyproject, "_run_mypy", return_value=ok_result()) as mock_mypy,
    ):
        yield PatchedMypyApply(
            boost=mypy_boost_with_pyproject,
            mock_uv=mock_uv,
            mock_git=mock_git,
            mock_mypy=mock_mypy,
        )


# =============================================================================
# PRECONDITIONS
# =============================================================================


def test_raises_skip_when_uv_nonzero(
    mypy_boost_with_pyproject: MypyBoost, fail_result: SubprocessResultFactory
) -> None:
    with (
        patch("pimp_my_repo.core.boosts.add_package.run_uv", return_value=fail_result()),
        pytest.raises(BoostSkippedError, match="uv is not available"),
    ):
        mypy_boost_with_pyproject.apply()


def test_raises_skip_when_uv_raises_file_not_found(mypy_boost_with_pyproject: MypyBoost) -> None:
    with (
        patch("pimp_my_repo.core.boosts.add_package.run_uv", side_effect=FileNotFoundError),
        pytest.raises(BoostSkippedError, match="uv is not installed"),
    ):
        mypy_boost_with_pyproject.apply()


def test_raises_skip_when_uv_raises_oserror(mypy_boost_with_pyproject: MypyBoost) -> None:
    with (
        patch("pimp_my_repo.core.boosts.add_package.run_uv", side_effect=OSError),
        pytest.raises(BoostSkippedError, match="uv is not installed"),
    ):
        mypy_boost_with_pyproject.apply()


def test_raises_skip_when_no_pyproject(mypy_boost: MypyBoost, ok_result: SubprocessResultFactory) -> None:
    with (
        patch.object(mypy_boost, "_run_uv", return_value=ok_result()),
        pytest.raises(BoostSkippedError, match=r"No pyproject\.toml found"),
    ):
        mypy_boost.apply()


# =============================================================================
# PARSE VIOLATIONS
# =============================================================================


def test_parses_single_violation(mypy_boost: MypyBoost) -> None:
    output = 'src/foo.py:10: error: Argument 1 has incompatible type "str"  [arg-type]'
    assert mypy_boost._parse_violations(output) == {_vl("src/foo.py", 10): {"arg-type"}}  # noqa: SLF001


def test_parses_violations_on_different_lines(mypy_boost: MypyBoost) -> None:
    output = "src/foo.py:10: error: Error A  [arg-type]\nsrc/foo.py:20: error: Error B  [union-attr]\n"
    result = mypy_boost._parse_violations(output)  # noqa: SLF001
    assert result == {
        _vl("src/foo.py", 10): {"arg-type"},
        _vl("src/foo.py", 20): {"union-attr"},
    }


def test_accumulates_multiple_codes_on_same_line(mypy_boost: MypyBoost) -> None:
    output = "src/foo.py:5: error: First error  [arg-type]\nsrc/foo.py:5: error: Second error  [return-value]\n"
    result = mypy_boost._parse_violations(output)  # noqa: SLF001
    assert result == {_vl("src/foo.py", 5): {"arg-type", "return-value"}}


def test_parses_violations_across_multiple_files(mypy_boost: MypyBoost) -> None:
    output = "src/foo.py:1: error: Error in foo  [misc]\nsrc/bar.py:2: error: Error in bar  [assignment]\n"
    result = mypy_boost._parse_violations(output)  # noqa: SLF001
    assert _vl("src/foo.py", 1) in result
    assert _vl("src/bar.py", 2) in result


def test_ignores_note_lines(mypy_boost: MypyBoost) -> None:
    output = "src/foo.py:10: error: Some error  [misc]\nsrc/foo.py:10: note: See https://mypy.rtfd.io\n"
    assert len(mypy_boost._parse_violations(output)) == 1  # noqa: SLF001


def test_ignores_errors_without_bracket_code(mypy_boost: MypyBoost) -> None:
    output = "src/foo.py:10: error: Some error without a code\n"
    assert mypy_boost._parse_violations(output) == {}  # noqa: SLF001


def test_ignores_summary_line(mypy_boost: MypyBoost) -> None:
    output = "src/foo.py:10: error: Some error  [misc]\nFound 1 error in 1 file (checked 5 source files)\n"
    assert len(mypy_boost._parse_violations(output)) == 1  # noqa: SLF001


def test_empty_output(mypy_boost: MypyBoost) -> None:
    assert mypy_boost._parse_violations("") == {}  # noqa: SLF001


def test_success_output(mypy_boost: MypyBoost) -> None:
    assert mypy_boost._parse_violations("Success: no issues found in 5 source files\n") == {}  # noqa: SLF001


# =============================================================================
# APPLY TYPE IGNORES
# =============================================================================


def test_adds_ignore_comment_to_clean_line(mock_repo: RepositoryController, mypy_boost: MypyBoost) -> None:
    mock_repo.add_file("src/foo.py", "x: int = 'hello'\n")
    mypy_boost._apply_type_ignores({_vl("src/foo.py", 1): {"assignment"}})  # noqa: SLF001
    assert "# type: ignore[assignment]" in (mock_repo.path / "src/foo.py").read_text()


def test_merges_new_code_with_existing_ignore(mock_repo: RepositoryController, mypy_boost: MypyBoost) -> None:
    mock_repo.add_file("src/foo.py", "x = foo()  # type: ignore[no-untyped-call]\n")
    mypy_boost._apply_type_ignores({_vl("src/foo.py", 1): {"return-value"}})  # noqa: SLF001
    content = (mock_repo.path / "src/foo.py").read_text()
    assert "no-untyped-call" in content
    assert "return-value" in content
    assert content.count("# type: ignore") == 1


def test_merges_multiple_new_codes_on_same_line(mock_repo: RepositoryController, mypy_boost: MypyBoost) -> None:
    mock_repo.add_file("src/foo.py", "x: int = 'hello'\n")
    mypy_boost._apply_type_ignores({_vl("src/foo.py", 1): {"assignment", "arg-type"}})  # noqa: SLF001
    content = (mock_repo.path / "src/foo.py").read_text()
    assert "# type: ignore[" in content
    assert "assignment" in content
    assert "arg-type" in content


def test_handles_multiple_lines_in_same_file(mock_repo: RepositoryController, mypy_boost: MypyBoost) -> None:
    mock_repo.add_file("src/foo.py", "a: int = 'x'\nb: str = 1\n")
    mypy_boost._apply_type_ignores(  # noqa: SLF001
        {
            _vl("src/foo.py", 1): {"assignment"},
            _vl("src/foo.py", 2): {"assignment"},
        }
    )
    lines = (mock_repo.path / "src/foo.py").read_text().splitlines()
    assert "# type: ignore[assignment]" in lines[0]
    assert "# type: ignore[assignment]" in lines[1]


def test_handles_multiple_files(mock_repo: RepositoryController, mypy_boost: MypyBoost) -> None:
    mock_repo.add_file("src/foo.py", "x: int = 'hello'\n")
    mock_repo.add_file("src/bar.py", "y: str = 42\n")
    mypy_boost._apply_type_ignores(  # noqa: SLF001
        {
            _vl("src/foo.py", 1): {"assignment"},
            _vl("src/bar.py", 1): {"assignment"},
        }
    )
    assert "# type: ignore" in (mock_repo.path / "src/foo.py").read_text()
    assert "# type: ignore" in (mock_repo.path / "src/bar.py").read_text()


def test_skips_missing_file_without_raising(mypy_boost: MypyBoost) -> None:
    mypy_boost._apply_type_ignores({_vl("nonexistent.py", 1): {"misc"}})  # noqa: SLF001


def test_type_ignore_codes_sorted_alphabetically(mock_repo: RepositoryController, mypy_boost: MypyBoost) -> None:
    mock_repo.add_file("src/foo.py", "x: int = 'hello'\n")
    mypy_boost._apply_type_ignores({_vl("src/foo.py", 1): {"misc", "arg-type", "assignment"}})  # noqa: SLF001
    content = (mock_repo.path / "src/foo.py").read_text()
    arg_type_pos = content.index("arg-type")
    assignment_pos = content.index("assignment")
    misc_pos = content.index("misc")
    assert arg_type_pos < assignment_pos < misc_pos


def test_type_ignore_preserves_existing_line_content(mock_repo: RepositoryController, mypy_boost: MypyBoost) -> None:
    mock_repo.add_file("src/foo.py", "result = some_func(arg1, arg2)  # business logic\n")
    mypy_boost._apply_type_ignores({_vl("src/foo.py", 1): {"misc"}})  # noqa: SLF001
    content = (mock_repo.path / "src/foo.py").read_text()
    assert "result = some_func(arg1, arg2)" in content
    assert "# type: ignore[misc]" in content


# =============================================================================
# ENSURE MYPY CONFIG
# =============================================================================


def test_adds_mypy_section_when_missing(mock_repo: RepositoryController, mypy_boost: MypyBoost) -> None:
    mock_repo.add_file("pyproject.toml", "[project]\nname = 'test'\n")
    data = mypy_boost._read_pyproject()  # noqa: SLF001
    data = mypy_boost._ensure_mypy_config(data)  # noqa: SLF001
    mypy_boost._write_pyproject(data)  # noqa: SLF001
    content = (mock_repo.path / "pyproject.toml").read_text()
    assert "[tool.mypy]" in content
    assert "strict = true" in content


def test_adds_tool_section_when_fully_absent(mock_repo: RepositoryController, mypy_boost: MypyBoost) -> None:
    mock_repo.add_file("pyproject.toml", "[project]\nname = 'test'\n")
    data = mypy_boost._read_pyproject()  # noqa: SLF001
    data = mypy_boost._ensure_mypy_config(data)  # noqa: SLF001
    assert "tool" in data
    assert "mypy" in data["tool"]  # type: ignore[operator]


def test_preserves_existing_tool_sections(mock_repo: RepositoryController, mypy_boost: MypyBoost) -> None:
    mock_repo.add_file("pyproject.toml", "[project]\nname = 'test'\n\n[tool.ruff]\nline-length = 120\n")
    data = mypy_boost._read_pyproject()  # noqa: SLF001
    data = mypy_boost._ensure_mypy_config(data)  # noqa: SLF001
    mypy_boost._write_pyproject(data)  # noqa: SLF001
    content = (mock_repo.path / "pyproject.toml").read_text()
    assert "[tool.ruff]" in content
    assert "line-length = 120" in content
    assert "[tool.mypy]" in content


def test_sets_strict_true_on_existing_mypy_section(mock_repo: RepositoryController, mypy_boost: MypyBoost) -> None:
    mock_repo.add_file("pyproject.toml", "[tool.mypy]\nstrict = false\n")
    data = mypy_boost._read_pyproject()  # noqa: SLF001
    data = mypy_boost._ensure_mypy_config(data)  # noqa: SLF001
    mypy_boost._write_pyproject(data)  # noqa: SLF001
    content = (mock_repo.path / "pyproject.toml").read_text()
    assert "strict = true" in content


# =============================================================================
# APPLY
# =============================================================================


def test_apply_calls_uv_add_mypy(patched_mypy_apply: PatchedMypyApply) -> None:
    with patch("pimp_my_repo.core.boosts.add_package.add_package_with_uv") as mock_add:
        patched_mypy_apply.boost.apply()
        mock_add.assert_called_once_with(patched_mypy_apply.boost.tools.repo_path, "mypy", dev=True)


def test_apply_writes_strict_config_to_pyproject(
    mock_repo: RepositoryController, patched_mypy_apply: PatchedMypyApply
) -> None:
    patched_mypy_apply.boost.apply()
    content = (mock_repo.path / "pyproject.toml").read_text()
    assert "strict = true" in content


def test_apply_makes_intermediate_git_commit(patched_mypy_apply: PatchedMypyApply) -> None:
    patched_mypy_apply.boost.apply()
    commit_calls = [c for c in patched_mypy_apply.mock_git.call_args_list if "commit" in c.args]
    assert len(commit_calls) >= 1


def test_apply_runs_mypy_once_when_already_clean(patched_mypy_apply: PatchedMypyApply) -> None:
    patched_mypy_apply.boost.apply()
    patched_mypy_apply.mock_mypy.assert_called_once()


def test_apply_inserts_type_ignore_on_violation(
    mock_repo: RepositoryController,
    patched_mypy_apply: PatchedMypyApply,
    fail_result: SubprocessResultFactory,
    ok_result: SubprocessResultFactory,
) -> None:
    mock_repo.add_file("src/foo.py", "x: int = 'hello'\n")
    patched_mypy_apply.mock_mypy.side_effect = [
        fail_result("src/foo.py:1: error: Some error  [assignment]\n"),
        ok_result(),
    ]
    patched_mypy_apply.boost.apply()
    assert "# type: ignore[assignment]" in (mock_repo.path / "src/foo.py").read_text()


def test_apply_iterates_until_mypy_passes(
    mock_repo: RepositoryController,
    patched_mypy_apply: PatchedMypyApply,
    fail_result: SubprocessResultFactory,
    ok_result: SubprocessResultFactory,
) -> None:
    mock_repo.add_file("src/foo.py", "x: int = 'hello'\n")
    patched_mypy_apply.mock_mypy.side_effect = [
        fail_result("src/foo.py:1: error: Error 1  [assignment]\n"),
        fail_result("src/foo.py:1: error: Error 2  [misc]\n"),
        ok_result(),
    ]
    patched_mypy_apply.boost.apply()
    assert patched_mypy_apply.mock_mypy.call_count == 3  # noqa: PLR2004


def test_apply_stops_after_max_iterations(
    mock_repo: RepositoryController,
    patched_mypy_apply: PatchedMypyApply,
    fail_result: SubprocessResultFactory,
) -> None:
    mock_repo.add_file("src/foo.py", "x: int = 'hello'\n")
    patched_mypy_apply.mock_mypy.return_value = fail_result("src/foo.py:1: error: Persistent error  [misc]\n")
    patched_mypy_apply.boost.apply()
    assert patched_mypy_apply.mock_mypy.call_count == _MAX_MYPY_ITERATIONS


def test_apply_stops_early_when_no_parseable_violations(
    patched_mypy_apply: PatchedMypyApply,
    fail_result: SubprocessResultFactory,
) -> None:
    patched_mypy_apply.mock_mypy.return_value = fail_result("src/foo.py:1: error: Cannot import module\n")
    patched_mypy_apply.boost.apply()
    patched_mypy_apply.mock_mypy.assert_called_once()


# =============================================================================
# MISC
# =============================================================================


def test_commit_message(mypy_boost: MypyBoost) -> None:
    assert mypy_boost.commit_message() == "✅ Silence mypy violations"


def test_get_name() -> None:
    assert MypyBoost.get_name() == "mypy"
