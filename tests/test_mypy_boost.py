"""Tests for Mypy boost implementation."""

from dataclasses import dataclass
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from pimp_my_repo.core.boosts.base import BoostSkippedError
from pimp_my_repo.core.boosts.mypy import _MAX_MYPY_ITERATIONS, DmypyBoost, MypyBoost, ViolationLocation

if TYPE_CHECKING:
    from collections.abc import Generator

    from pimp_my_repo.core.tools.boost_tools import BoostTools
    from pimp_my_repo.core.tools.repo import RepositoryController
    from tests.conftest import SubprocessResultFactory

_vl = ViolationLocation


@pytest.fixture
def mypy_boost(boost_tools: BoostTools) -> MypyBoost:
    """Create a MypyBoost instance without pyproject.toml."""
    return MypyBoost(boost_tools)


@pytest.fixture
def dmypy_boost(boost_tools: BoostTools) -> DmypyBoost:
    """Create a DmypyBoost instance without pyproject.toml."""
    return DmypyBoost(boost_tools)


@pytest.fixture
def mypy_boost_with_pyproject(repo_controller: RepositoryController, boost_tools: BoostTools) -> MypyBoost:
    """Create a MypyBoost instance with a minimal pyproject.toml."""
    repo_controller.write_file("pyproject.toml", "[project]\nname = 'test'\nversion = '0.1.0'\n")
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
        patch.object(mypy_boost_with_pyproject.tools.uv, "exec", return_value=ok_result()) as mock_uv,
        patch.object(mypy_boost_with_pyproject.tools.git, "commit") as mock_git,
        patch.object(mypy_boost_with_pyproject, "_run_type_checker", return_value=ok_result()) as mock_mypy,
    ):
        yield PatchedMypyApply(
            boost=mypy_boost_with_pyproject,
            mock_uv=mock_uv,
            mock_git=mock_git,
            mock_mypy=mock_mypy,
        )


@dataclass
class PatchedMypyApplyWithAddPackage:
    """Pre-patched MypyBoost with subprocess and add_package mocks wired for apply()."""

    boost: MypyBoost
    mock_uv: MagicMock
    mock_git: MagicMock
    mock_mypy: MagicMock
    mock_add_package: MagicMock


@pytest.fixture
def patched_mypy_apply_with_add_package(
    mypy_boost_with_pyproject: MypyBoost,
    ok_result: SubprocessResultFactory,
) -> Generator[PatchedMypyApplyWithAddPackage]:
    """Yield a MypyBoost with all subprocess and add_package calls pre-mocked."""
    with (
        patch.object(mypy_boost_with_pyproject.tools.uv, "exec", return_value=ok_result()) as mock_uv,
        patch.object(mypy_boost_with_pyproject.tools.git, "commit") as mock_git,
        patch.object(mypy_boost_with_pyproject, "_run_type_checker", return_value=ok_result()) as mock_mypy,
        patch.object(mypy_boost_with_pyproject.tools.uv, "add_package") as mock_add_package,
    ):
        yield PatchedMypyApplyWithAddPackage(
            boost=mypy_boost_with_pyproject,
            mock_uv=mock_uv,
            mock_git=mock_git,
            mock_mypy=mock_mypy,
            mock_add_package=mock_add_package,
        )


@pytest.fixture
def mypy_boost_uv_failing(
    mypy_boost_with_pyproject: MypyBoost,
    fail_result: SubprocessResultFactory,
) -> Generator[MypyBoost]:
    """Yield a MypyBoost where uv.run returns a non-zero result."""
    with patch.object(mypy_boost_with_pyproject.tools.uv, "exec", return_value=fail_result()):
        yield mypy_boost_with_pyproject


@pytest.fixture
def mypy_boost_uv_file_not_found(mypy_boost_with_pyproject: MypyBoost) -> Generator[MypyBoost]:
    """Yield a MypyBoost where uv.run raises FileNotFoundError."""
    with patch.object(mypy_boost_with_pyproject.tools.uv, "exec", side_effect=FileNotFoundError):
        yield mypy_boost_with_pyproject


@pytest.fixture
def mypy_boost_uv_oserror(mypy_boost_with_pyproject: MypyBoost) -> Generator[MypyBoost]:
    """Yield a MypyBoost where uv.run raises OSError."""
    with patch.object(mypy_boost_with_pyproject.tools.uv, "exec", side_effect=OSError):
        yield mypy_boost_with_pyproject


@pytest.fixture
def mypy_boost_uv_ok(
    mypy_boost: MypyBoost,
    ok_result: SubprocessResultFactory,
) -> Generator[MypyBoost]:
    """Yield a MypyBoost (no pyproject) where uv.run returns ok."""
    with patch.object(mypy_boost.tools.uv, "exec", return_value=ok_result()):
        yield mypy_boost


# =============================================================================
# PRECONDITIONS
# =============================================================================


def test_raises_skip_when_uv_nonzero(mypy_boost_uv_failing: MypyBoost) -> None:
    with pytest.raises(BoostSkippedError, match="uv is not available"):
        mypy_boost_uv_failing.apply()


def test_raises_skip_when_uv_raises_file_not_found(mypy_boost_uv_file_not_found: MypyBoost) -> None:
    with pytest.raises(BoostSkippedError, match="uv is not installed"):
        mypy_boost_uv_file_not_found.apply()


def test_raises_skip_when_uv_raises_oserror(mypy_boost_uv_oserror: MypyBoost) -> None:
    with pytest.raises(BoostSkippedError, match="uv is not installed"):
        mypy_boost_uv_oserror.apply()


@pytest.mark.smoke
def test_raises_skip_when_no_pyproject(mypy_boost_uv_ok: MypyBoost) -> None:
    with pytest.raises(BoostSkippedError, match=r"No pyproject\.toml found"):
        mypy_boost_uv_ok.apply()


# =============================================================================
# PARSE VIOLATIONS
# =============================================================================


@pytest.mark.smoke
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


def test_parses_violation_with_column_number(mypy_boost: MypyBoost) -> None:
    output = "src/foo.py:10:5: error: Incompatible type  [arg-type]"
    assert mypy_boost._parse_violations(output) == {_vl("src/foo.py", 10): {"arg-type"}}  # noqa: SLF001


def test_parses_note_uncovered_code(mypy_boost: MypyBoost) -> None:
    output = 'src/foo.py:10: note: Error code "misc" not covered by "type: ignore" comment'
    assert mypy_boost._parse_violations(output) == {_vl("src/foo.py", 10): {"misc"}}  # noqa: SLF001


def test_parses_note_uncovered_code_with_column(mypy_boost: MypyBoost) -> None:
    output = 'src/foo.py:10:1: note: Error code "misc" not covered by "type: ignore" comment'
    assert mypy_boost._parse_violations(output) == {_vl("src/foo.py", 10): {"misc"}}  # noqa: SLF001


def test_parses_unused_ignore_from_note(mypy_boost: MypyBoost) -> None:
    """unused-ignore is reported as a note: Error code not covered line."""
    output = 'src/foo.py:5: note: Error code "unused-ignore" not covered by "type: ignore" comment'
    assert mypy_boost._parse_violations(output) == {_vl("src/foo.py", 5): {"unused-ignore"}}  # noqa: SLF001


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
    mock_repo.write_file("src/foo.py", "x: int = 'hello'\n")
    mypy_boost._apply_type_ignores({_vl("src/foo.py", 1): {"assignment"}})  # noqa: SLF001
    assert "# type: ignore[assignment]" in (mock_repo.path / "src/foo.py").read_text()


def test_merges_new_code_with_existing_ignore(mock_repo: RepositoryController, mypy_boost: MypyBoost) -> None:
    mock_repo.write_file("src/foo.py", "x = foo()  # type: ignore[no-untyped-call]\n")
    mypy_boost._apply_type_ignores({_vl("src/foo.py", 1): {"return-value"}})  # noqa: SLF001
    content = (mock_repo.path / "src/foo.py").read_text()
    assert "no-untyped-call" in content
    assert "return-value" in content
    assert content.count("# type: ignore") == 1


def test_merges_multiple_new_codes_on_same_line(mock_repo: RepositoryController, mypy_boost: MypyBoost) -> None:
    mock_repo.write_file("src/foo.py", "x: int = 'hello'\n")
    mypy_boost._apply_type_ignores({_vl("src/foo.py", 1): {"assignment", "arg-type"}})  # noqa: SLF001
    content = (mock_repo.path / "src/foo.py").read_text()
    assert "# type: ignore[" in content
    assert "assignment" in content
    assert "arg-type" in content


def test_handles_multiple_lines_in_same_file(mock_repo: RepositoryController, mypy_boost: MypyBoost) -> None:
    mock_repo.write_file("src/foo.py", "a: int = 'x'\nb: str = 1\n")
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
    mock_repo.write_file("src/foo.py", "x: int = 'hello'\n")
    mock_repo.write_file("src/bar.py", "y: str = 42\n")
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
    mock_repo.write_file("src/foo.py", "x: int = 'hello'\n")
    mypy_boost._apply_type_ignores({_vl("src/foo.py", 1): {"misc", "arg-type", "assignment"}})  # noqa: SLF001
    content = (mock_repo.path / "src/foo.py").read_text()
    arg_type_pos = content.index("arg-type")
    assignment_pos = content.index("assignment")
    misc_pos = content.index("misc")
    assert arg_type_pos < assignment_pos < misc_pos


def test_type_ignore_preserves_existing_line_content(mock_repo: RepositoryController, mypy_boost: MypyBoost) -> None:
    mock_repo.write_file("src/foo.py", "result = some_func(arg1, arg2)  # business logic\n")
    mypy_boost._apply_type_ignores({_vl("src/foo.py", 1): {"misc"}})  # noqa: SLF001
    content = (mock_repo.path / "src/foo.py").read_text()
    assert "result = some_func(arg1, arg2)" in content
    assert "# type: ignore[misc]" in content


def test_type_ignore_placed_before_noqa(mock_repo: RepositoryController, mypy_boost: MypyBoost) -> None:
    mock_repo.write_file("src/foo.py", "x: int = 'hello'  # noqa: E501\n")
    mypy_boost._apply_type_ignores({_vl("src/foo.py", 1): {"assignment"}})  # noqa: SLF001
    content = (mock_repo.path / "src/foo.py").read_text()
    type_ignore_pos = content.index("# type: ignore")
    noqa_pos = content.index("# noqa")
    assert type_ignore_pos < noqa_pos


def test_bare_type_ignore_kept_as_is(mock_repo: RepositoryController, mypy_boost: MypyBoost) -> None:
    """A bare # type: ignore (no codes) already suppresses everything; leave it unchanged."""
    original = "x: int = 'hello'  # type: ignore\n"
    mock_repo.write_file("src/foo.py", original)
    mypy_boost._apply_type_ignores({_vl("src/foo.py", 1): {"assignment"}})  # noqa: SLF001
    assert (mock_repo.path / "src/foo.py").read_text() == original


def test_removes_type_ignore_for_unused_ignore(mock_repo: RepositoryController, mypy_boost: MypyBoost) -> None:
    mock_repo.write_file("src/foo.py", "x = foo()  # type: ignore[no-untyped-call]\n")
    mypy_boost._apply_type_ignores({_vl("src/foo.py", 1): {"unused-ignore"}})  # noqa: SLF001
    content = (mock_repo.path / "src/foo.py").read_text()
    assert "# type: ignore" not in content
    assert "x = foo()" in content


def test_removes_type_ignore_preserves_trailing_comma(mock_repo: RepositoryController, mypy_boost: MypyBoost) -> None:
    """Trailing comma before # type: ignore is code syntax and must not be stripped."""
    mock_repo.write_file("src/foo.py", '    "key": self.quote_name(col),  # type: ignore[no-untyped-call]\n')
    mypy_boost._apply_type_ignores({_vl("src/foo.py", 1): {"unused-ignore"}})  # noqa: SLF001
    content = (mock_repo.path / "src/foo.py").read_text()
    assert "# type: ignore" not in content
    assert "self.quote_name(col)," in content


def test_remove_codes_preserves_trailing_comma(mock_repo: RepositoryController, mypy_boost: MypyBoost) -> None:
    """Trailing comma before # type: ignore is preserved when specific codes are removed."""
    mock_repo.write_file("src/foo.py", '    "key": self.quote_name(col),  # type: ignore[no-untyped-call]\n')
    mypy_boost._apply_type_ignores({_vl("src/foo.py", 1): {"!no-untyped-call"}})  # noqa: SLF001
    content = (mock_repo.path / "src/foo.py").read_text()
    assert "# type: ignore" not in content
    assert "self.quote_name(col)," in content


def test_conflicting_error_and_unused_ignore_prefers_error(
    mock_repo: RepositoryController, mypy_boost: MypyBoost
) -> None:
    """When one tool reports an error [X] and another reports unused-ignore [X], keep the ignore."""
    mock_repo.write_file("src/foo.py", "x: int = 'hello'  # type: ignore[assignment]\n")
    mypy_boost._apply_type_ignores({_vl("src/foo.py", 1): {"assignment", "!assignment"}})  # noqa: SLF001
    content = (mock_repo.path / "src/foo.py").read_text()
    assert "# type: ignore[assignment]" in content


def test_unused_ignore_with_other_codes_keeps_others(mock_repo: RepositoryController, mypy_boost: MypyBoost) -> None:
    """When unused-ignore accompanies real codes, keep the real codes only."""
    mock_repo.write_file("src/foo.py", "x = foo()  # type: ignore[no-untyped-call]\n")
    mypy_boost._apply_type_ignores({_vl("src/foo.py", 1): {"unused-ignore", "return-value"}})  # noqa: SLF001
    content = (mock_repo.path / "src/foo.py").read_text()
    assert "return-value" in content
    assert "unused-ignore" not in content


def test_type_ignore_placed_before_triple_quote_in_function_call(
    mock_repo: RepositoryController, mypy_boost: MypyBoost
) -> None:
    """type: ignore must be placed before \"\"\" in function calls to avoid being inside the string."""
    mock_repo.write_file("src/foo.py", 'result = func("""\ncontent\n""")\n')
    mypy_boost._apply_type_ignores({_vl("src/foo.py", 1): {"no-untyped-call"}})  # noqa: SLF001
    lines = (mock_repo.path / "src/foo.py").read_text().splitlines()
    assert "# type: ignore[no-untyped-call]" in lines[0]
    assert '"""' not in lines[0]


def test_type_ignore_placed_on_closing_triple_quote_in_assignment(
    mock_repo: RepositoryController, mypy_boost: MypyBoost
) -> None:
    """For assignments, type: ignore goes on the CLOSING triple-quote line.

    mypy attributes the assignment error to the opening triple-quote line but recognises
    a type: ignore on the closing line as suppressing it. Placing it on the opening line
    via a () wrapper is removed by ruff UP034, causing an oscillation loop.
    """
    mock_repo.write_file("src/foo.py", 'sql = """\nCREATE TABLE\n"""\n')
    mypy_boost._apply_type_ignores({_vl("src/foo.py", 1): {"assignment"}})  # noqa: SLF001
    content = (mock_repo.path / "src/foo.py").read_text()
    closing_line = content.splitlines()[-1]
    assert "# type: ignore[assignment]" in content
    assert '"""' in closing_line
    assert "# type: ignore[assignment]" in closing_line


def test_type_ignore_on_line_with_single_quoted_triple_double_quote(
    mock_repo: RepositoryController, mypy_boost: MypyBoost
) -> None:
    """A single-quoted string containing '\"\"\"' must not be confused with a triple-quote opener.

    Without this fix, _find_unclosed_triple_quote_pos mistakes '\"\"\"' for an unclosed \"\"\"
    and places the type: ignore on some later line instead of the current one.
    """
    mock_repo.write_file("src/foo.py", """x = '\"\"\"'\n""")
    mypy_boost._apply_type_ignores({_vl("src/foo.py", 1): {"attr-defined"}})  # noqa: SLF001
    content = (mock_repo.path / "src/foo.py").read_text()
    assert "# type: ignore[attr-defined]" in content.splitlines()[0]


def test_merges_two_type_ignore_comments_into_one(mock_repo: RepositoryController, mypy_boost: MypyBoost) -> None:
    """Multiple type: ignore comments on a line must be merged into a single one."""
    mock_repo.write_file("src/foo.py", "x = foo()  # type: ignore[arg-type]  # type: ignore[return-value]\n")
    mypy_boost._apply_type_ignores({_vl("src/foo.py", 1): {"misc"}})  # noqa: SLF001
    content = (mock_repo.path / "src/foo.py").read_text()
    assert content.count("# type: ignore") == 1
    assert "arg-type" in content
    assert "return-value" in content
    assert "misc" in content


# =============================================================================
# ENSURE MYPY CONFIG
# =============================================================================


def test_adds_mypy_section_when_missing(mock_repo: RepositoryController, mypy_boost: MypyBoost) -> None:
    mock_repo.write_file("pyproject.toml", "[project]\nname = 'test'\n")
    data = mypy_boost.tools.pyproject.read()
    data = mypy_boost._ensure_mypy_config(data)  # noqa: SLF001
    mypy_boost.tools.pyproject.write(data)
    content = (mock_repo.path / "pyproject.toml").read_text()
    assert "[tool.mypy]" in content
    assert "strict = true" in content


def test_adds_tool_section_when_fully_absent(mock_repo: RepositoryController, mypy_boost: MypyBoost) -> None:
    mock_repo.write_file("pyproject.toml", "[project]\nname = 'test'\n")
    data = mypy_boost.tools.pyproject.read()
    data = mypy_boost._ensure_mypy_config(data)  # noqa: SLF001
    assert "tool" in data
    assert "mypy" in data["tool"]  # type: ignore[operator]


def test_preserves_existing_tool_sections(mock_repo: RepositoryController, mypy_boost: MypyBoost) -> None:
    mock_repo.write_file("pyproject.toml", "[project]\nname = 'test'\n\n[tool.ruff]\nline-length = 120\n")
    data = mypy_boost.tools.pyproject.read()
    data = mypy_boost._ensure_mypy_config(data)  # noqa: SLF001
    mypy_boost.tools.pyproject.write(data)
    content = (mock_repo.path / "pyproject.toml").read_text()
    assert "[tool.ruff]" in content
    assert "line-length = 120" in content
    assert "[tool.mypy]" in content


def test_sets_strict_true_on_existing_mypy_section(mock_repo: RepositoryController, mypy_boost: MypyBoost) -> None:
    mock_repo.write_file("pyproject.toml", "[tool.mypy]\nstrict = false\n")
    data = mypy_boost.tools.pyproject.read()
    data = mypy_boost._ensure_mypy_config(data)  # noqa: SLF001
    mypy_boost.tools.pyproject.write(data)
    content = (mock_repo.path / "pyproject.toml").read_text()
    assert "strict = true" in content


# =============================================================================
# _RUN_TYPE_CHECKER
# =============================================================================


def test_clear_mypy_cache_removes_cache_dir_and_dmypy_json(
    mock_repo: RepositoryController, mypy_boost: MypyBoost
) -> None:
    cache_dir = mock_repo.path / ".mypy_cache"
    cache_dir.mkdir()
    (cache_dir / "stale.json").write_text("{}")
    dmypy_json = mock_repo.path / ".dmypy.json"
    dmypy_json.write_text("{}")

    mypy_boost._clear_mypy_cache()  # noqa: SLF001

    assert not cache_dir.exists()
    assert not dmypy_json.exists()


def test_mypy_clears_cache_before_and_after_run(mypy_boost: MypyBoost, ok_result: SubprocessResultFactory) -> None:
    call_order: list[str] = []

    def record_exec(*_args: str, **_kwargs: object) -> object:
        call_order.append("mypy")
        return ok_result()

    with (
        patch.object(mypy_boost, "_clear_mypy_cache", side_effect=lambda: call_order.append("clear")),
        patch.object(mypy_boost.tools.uv, "exec", side_effect=record_exec) as mock_exec,
    ):
        mypy_boost._run_type_checker()  # noqa: SLF001

    assert call_order == ["clear", "mypy", "clear"], "cache must be cleared before and after mypy"
    mock_exec.assert_called_once_with("run", "--no-sync", "mypy", ".", check=False, log_on_error=False)


def test_dmypy_clears_cache_before_kill_and_after_run(
    dmypy_boost: DmypyBoost, ok_result: SubprocessResultFactory
) -> None:
    """Cache must be cleared before dmypy kill and again after dmypy run."""
    call_order: list[str] = []

    def record_exec(*args: str, **_kwargs: object) -> object:
        call_order.append("kill" if "kill" in args else "dmypy_run")
        return ok_result()

    with (
        patch.object(dmypy_boost, "_clear_mypy_cache", side_effect=lambda: call_order.append("clear")),
        patch.object(dmypy_boost.tools.uv, "exec", side_effect=record_exec),
    ):
        dmypy_boost._run_type_checker()  # noqa: SLF001

    assert call_order == ["clear", "kill", "dmypy_run", "clear"], (
        "order must be: clear cache → kill daemon → run → clear cache"
    )


# =============================================================================
# ADD DMYPY TO GITIGNORE
# =============================================================================


def test_add_dmypy_creates_gitignore_when_absent(mock_repo: RepositoryController, dmypy_boost: DmypyBoost) -> None:
    dmypy_boost._add_dmypy_to_gitignore()  # noqa: SLF001
    assert (mock_repo.path / ".gitignore").read_text() == ".dmypy.json\n"


def test_add_dmypy_appends_to_existing_gitignore(mock_repo: RepositoryController, dmypy_boost: DmypyBoost) -> None:
    mock_repo.write_file(".gitignore", "*.pyc\n__pycache__/\n")
    dmypy_boost._add_dmypy_to_gitignore()  # noqa: SLF001
    content = (mock_repo.path / ".gitignore").read_text()
    assert "*.pyc" in content
    assert ".dmypy.json" in content


def test_add_dmypy_idempotent(mock_repo: RepositoryController, dmypy_boost: DmypyBoost) -> None:
    mock_repo.write_file(".gitignore", ".dmypy.json\n")
    dmypy_boost._add_dmypy_to_gitignore()  # noqa: SLF001
    assert (mock_repo.path / ".gitignore").read_text().count(".dmypy.json") == 1


def test_add_dmypy_adds_newline_before_entry(mock_repo: RepositoryController, dmypy_boost: DmypyBoost) -> None:
    mock_repo.write_file(".gitignore", "*.pyc")  # no trailing newline
    dmypy_boost._add_dmypy_to_gitignore()  # noqa: SLF001
    content = (mock_repo.path / ".gitignore").read_text()
    assert content == "*.pyc\n.dmypy.json\n"


# =============================================================================
# APPLY
# =============================================================================


@pytest.mark.smoke
def test_apply_calls_uv_add_mypy(patched_mypy_apply_with_add_package: PatchedMypyApplyWithAddPackage) -> None:
    patched_mypy_apply_with_add_package.boost.apply()
    patched_mypy_apply_with_add_package.mock_add_package.assert_called_once_with("mypy<1.21", group="lint")


def test_apply_writes_strict_config_to_pyproject(
    mock_repo: RepositoryController, patched_mypy_apply: PatchedMypyApply
) -> None:
    patched_mypy_apply.boost.apply()
    content = (mock_repo.path / "pyproject.toml").read_text()
    assert "strict = true" in content


def test_apply_makes_intermediate_git_commit(patched_mypy_apply: PatchedMypyApply) -> None:
    patched_mypy_apply.boost.apply()
    assert patched_mypy_apply.mock_git.call_count >= 1


def test_apply_runs_mypy_once_when_already_clean(patched_mypy_apply: PatchedMypyApply) -> None:
    patched_mypy_apply.boost.apply()
    patched_mypy_apply.mock_mypy.assert_called_once()


def test_apply_inserts_type_ignore_on_violation(
    mock_repo: RepositoryController,
    patched_mypy_apply: PatchedMypyApply,
    fail_result: SubprocessResultFactory,
    ok_result: SubprocessResultFactory,
) -> None:
    mock_repo.write_file("src/foo.py", "x: int = 'hello'\n")
    patched_mypy_apply.mock_mypy.side_effect = [
        fail_result("src/foo.py:1: error: Some error  [assignment]\n"),
        ok_result(),
    ]
    patched_mypy_apply.boost.apply()
    assert "# type: ignore[assignment]" in (mock_repo.path / "src/foo.py").read_text()


@pytest.mark.smoke
def test_apply_iterates_until_mypy_passes(
    mock_repo: RepositoryController,
    patched_mypy_apply: PatchedMypyApply,
    fail_result: SubprocessResultFactory,
    ok_result: SubprocessResultFactory,
) -> None:
    mock_repo.write_file("src/foo.py", "x: int = 'hello'\n")
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
    """MAX_ITERATIONS is the hard cap. In practice the loop stops earlier via no-progress detection."""
    mock_repo.write_file("src/foo.py", "x: int = 'hello'\n")
    patched_mypy_apply.mock_mypy.return_value = fail_result("src/foo.py:1: error: Persistent error  [misc]\n")
    patched_mypy_apply.boost.apply()
    assert patched_mypy_apply.mock_mypy.call_count <= _MAX_MYPY_ITERATIONS


def test_apply_stops_on_no_progress(
    mock_repo: RepositoryController,
    patched_mypy_apply: PatchedMypyApply,
    fail_result: SubprocessResultFactory,
) -> None:
    """Loop stops as soon as no file changes result from applying violations."""
    mock_repo.write_file("src/foo.py", "x: int = 'hello'\n")
    patched_mypy_apply.mock_mypy.return_value = fail_result("src/foo.py:1: error: Persistent error  [misc]\n")
    patched_mypy_apply.boost.apply()
    # Iteration 1: adds the ignore (file changes). Iteration 2: ignore already there, no change → stop.
    assert patched_mypy_apply.mock_mypy.call_count == 2  # noqa: PLR2004


def test_apply_stops_early_when_no_parseable_violations(
    patched_mypy_apply: PatchedMypyApply,
    fail_result: SubprocessResultFactory,
) -> None:
    patched_mypy_apply.mock_mypy.return_value = fail_result("src/foo.py:1: error: Cannot import module\n")
    patched_mypy_apply.boost.apply()
    patched_mypy_apply.mock_mypy.assert_called_once()


def test_apply_stops_when_conflicting_tools_make_no_file_changes(
    mock_repo: RepositoryController,
    patched_mypy_apply: PatchedMypyApply,
    fail_result: SubprocessResultFactory,
) -> None:
    """When tools disagree (error vs unused-ignore for the same code), error wins and the ignore is kept.

    Since no file changes result, the loop must stop instead of running to MAX_ITERATIONS.
    """
    mock_repo.write_file("src/foo.py", "x: int = 'hello'  # type: ignore[assignment]\n")
    # Simulates dmypy reporting both error [assignment] and unused-ignore [assignment] for the same line.
    conflicting_output = (
        "src/foo.py:1: error: Incompatible types  [assignment]\n"
        'src/foo.py:1: error: Unused "type: ignore[assignment]" comment  [unused-ignore]\n'
    )
    patched_mypy_apply.mock_mypy.return_value = fail_result(conflicting_output)
    patched_mypy_apply.boost.apply()
    assert patched_mypy_apply.mock_mypy.call_count < _MAX_MYPY_ITERATIONS


def test_excludes_uncoded_blocking_error_file_in_pyproject(
    mock_repo: RepositoryController,
    patched_mypy_apply: PatchedMypyApply,
    fail_result: SubprocessResultFactory,
    ok_result: SubprocessResultFactory,
) -> None:
    mypy_output = (
        'tests/pkg/wild.py: error: Source file found twice under different module names: "a" and "b"\n'
        "Found 1 error in 1 file (errors prevented further checking)\n"
    )
    patched_mypy_apply.mock_mypy.side_effect = [fail_result(mypy_output), ok_result()]
    patched_mypy_apply.boost.apply()
    content = (mock_repo.path / "pyproject.toml").read_text()
    # "found twice" errors exclude the parent directory, not just the specific file
    assert "tests/pkg/" in content
    assert "wild.py" not in content


def test_excludes_syntax_error_file_in_pyproject(
    mock_repo: RepositoryController,
    patched_mypy_apply: PatchedMypyApply,
    fail_result: SubprocessResultFactory,
    ok_result: SubprocessResultFactory,
) -> None:
    patched_mypy_apply.mock_mypy.side_effect = [
        fail_result("src/bad.py:5: error: Invalid syntax  [syntax]\n"),
        ok_result(),
    ]
    patched_mypy_apply.boost.apply()
    content = (mock_repo.path / "pyproject.toml").read_text()
    # re.escape produces "src/bad\.py"; TOML serializes the backslash as "\\" in the file
    assert r"src/bad\\.py" in content


def test_escalates_to_parent_dir_when_syntax_file_exclusion_fails(
    mock_repo: RepositoryController,
    patched_mypy_apply: PatchedMypyApply,
    fail_result: SubprocessResultFactory,
    ok_result: SubprocessResultFactory,
) -> None:
    """When file-level exclusion doesn't prevent mypy from reporting a syntax error, escalate.

    This happens e.g. when the file is imported during package discovery. Escalating to
    excluding the parent directory makes mypy skip the whole package.
    """
    syntax_error_output = "src/pkg/bad.py:5: error: Invalid syntax  [syntax]\n"
    patched_mypy_apply.mock_mypy.side_effect = [
        fail_result(syntax_error_output),  # iteration 1: exclude src/pkg/bad.py (new)
        fail_result(syntax_error_output),  # iteration 2: file already excluded → escalate to src/pkg/
        ok_result(),  # iteration 3: mypy passes after parent-dir exclusion
    ]
    patched_mypy_apply.boost.apply()
    content = (mock_repo.path / "pyproject.toml").read_text()
    assert "src/pkg/" in content
    assert patched_mypy_apply.mock_mypy.call_count == 3  # noqa: PLR2004


def test_stops_when_syntax_file_already_excluded(
    patched_mypy_apply: PatchedMypyApply,
    fail_result: SubprocessResultFactory,
) -> None:
    """Even if escalation to parent dir can't make mypy stop, the loop still terminates.

    Iteration 1 excludes the file, iteration 2 escalates to the parent dir,
    iteration 3 finds nothing new to exclude and stops.
    """
    syntax_error_output = "src/bad.py:5: error: Invalid syntax  [syntax]\n"
    patched_mypy_apply.mock_mypy.return_value = fail_result(syntax_error_output)
    patched_mypy_apply.boost.apply()
    # Iteration 1: excludes src/bad.py (new file pattern).
    # Iteration 2: file already excluded → escalates to src/ (new parent pattern).
    # Iteration 3: both already excluded → no progress → stop.
    assert patched_mypy_apply.mock_mypy.call_count == 3  # noqa: PLR2004


def test_stops_when_uncoded_blocking_file_already_excluded(
    patched_mypy_apply: PatchedMypyApply,
    fail_result: SubprocessResultFactory,
) -> None:
    """Same convergence guarantee for uncoded blocking errors (e.g. 'found twice')."""
    mypy_output = (
        'tests/pkg/wild.py: error: Source file found twice under different module names: "a" and "b"\n'
        "Found 1 error in 1 file (errors prevented further checking)\n"
    )
    patched_mypy_apply.mock_mypy.return_value = fail_result(mypy_output)
    patched_mypy_apply.boost.apply()
    # Iteration 1: excludes tests/pkg/ (new). Iteration 2: already excluded, no progress → stop.
    assert patched_mypy_apply.mock_mypy.call_count == 2  # noqa: PLR2004


# =============================================================================
# MISC
# =============================================================================


def test_commit_message(mypy_boost: MypyBoost) -> None:
    assert mypy_boost.commit_message() == "✅ Silence mypy violations"


def test_get_name() -> None:
    assert MypyBoost.get_name() == "mypy"
