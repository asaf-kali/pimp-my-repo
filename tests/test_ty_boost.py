"""Tests for Ty boost implementation."""

from dataclasses import dataclass
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from pimp_my_repo.core.boosts.base import BoostSkipped
from pimp_my_repo.core.boosts.ty import _MAX_TY_ITERATIONS, TyBoost, ViolationLocation, _merge_ty_ignore

if TYPE_CHECKING:
    from collections.abc import Generator

    from pimp_my_repo.core.tools.boost_tools import BoostTools
    from pimp_my_repo.core.tools.repo import RepositoryController
    from tests.conftest import SubprocessResultFactory


@pytest.fixture
def ty_boost(boost_tools: BoostTools) -> TyBoost:
    return TyBoost(boost_tools)


@pytest.fixture
def ty_boost_with_pyproject(boost_tools: BoostTools, repo_controller: RepositoryController) -> TyBoost:
    repo_controller.write_file("pyproject.toml", "[project]\nname = 'test'\nversion = '0.1.0'\n")
    return TyBoost(boost_tools)


@dataclass
class PatchedTyApply:
    """Pre-patched TyBoost with all subprocess mocks wired for apply()."""

    boost: TyBoost
    mock_uv: MagicMock
    mock_git: MagicMock
    mock_check: MagicMock


@pytest.fixture
def patched_ty_apply(
    ty_boost_with_pyproject: TyBoost,
    ok_result: SubprocessResultFactory,
) -> Generator[PatchedTyApply]:
    """Yield a TyBoost with all subprocess calls pre-mocked to succeed."""
    with (
        patch.object(ty_boost_with_pyproject.tools.uv, "exec", return_value=ok_result()) as mock_uv,
        patch.object(ty_boost_with_pyproject.tools.git, "commit") as mock_git,
        patch.object(ty_boost_with_pyproject, "_run_ty_check", return_value=ok_result()) as mock_check,
    ):
        yield PatchedTyApply(
            boost=ty_boost_with_pyproject,
            mock_uv=mock_uv,
            mock_git=mock_git,
            mock_check=mock_check,
        )


@pytest.fixture
def ty_boost_uv_failing(
    ty_boost_with_pyproject: TyBoost,
    fail_result: SubprocessResultFactory,
) -> Generator[TyBoost]:
    with patch.object(ty_boost_with_pyproject.tools.uv, "exec", return_value=fail_result()):
        yield ty_boost_with_pyproject


@pytest.fixture
def ty_boost_uv_file_not_found(ty_boost_with_pyproject: TyBoost) -> Generator[TyBoost]:
    with patch.object(ty_boost_with_pyproject.tools.uv, "exec", side_effect=FileNotFoundError):
        yield ty_boost_with_pyproject


@pytest.fixture
def ty_boost_uv_ok(
    ty_boost: TyBoost,
    ok_result: SubprocessResultFactory,
) -> Generator[TyBoost]:
    with patch.object(ty_boost.tools.uv, "exec", return_value=ok_result()):
        yield ty_boost


# =============================================================================
# PRECONDITIONS
# =============================================================================


def test_raises_skip_when_uv_nonzero(ty_boost_uv_failing: TyBoost) -> None:
    with pytest.raises(BoostSkipped, match="uv is not available"):
        ty_boost_uv_failing.apply()


def test_raises_skip_when_uv_raises_file_not_found(ty_boost_uv_file_not_found: TyBoost) -> None:
    with pytest.raises(BoostSkipped, match="uv is not installed"):
        ty_boost_uv_file_not_found.apply()


@pytest.mark.smoke
def test_raises_skip_when_no_pyproject(ty_boost_uv_ok: TyBoost) -> None:
    with pytest.raises(BoostSkipped, match=r"No pyproject\.toml found"):
        ty_boost_uv_ok.apply()


# =============================================================================
# PARSE OUTPUT
# =============================================================================


@pytest.mark.smoke
def test_parses_single_violation(ty_boost: TyBoost) -> None:
    output = "src/foo.py:10:5: error[unresolved-import] Cannot resolve import 'foo'\n"
    result = ty_boost._parse_ty_output(output)  # noqa: SLF001
    assert result == {ViolationLocation("src/foo.py", 10): {"unresolved-import"}}


def test_parses_warning_as_violation(ty_boost: TyBoost) -> None:
    output = "src/foo.py:5:1: warning[possibly-unbound] 'x' may be unbound\n"
    result = ty_boost._parse_ty_output(output)  # noqa: SLF001
    assert result == {ViolationLocation("src/foo.py", 5): {"possibly-unbound"}}


def test_accumulates_multiple_codes_on_same_line(ty_boost: TyBoost) -> None:
    output = "src/foo.py:10:5: error[unresolved-import] ...\nsrc/foo.py:10:1: error[invalid-assignment] ...\n"
    result = ty_boost._parse_ty_output(output)  # noqa: SLF001
    assert result == {ViolationLocation("src/foo.py", 10): {"unresolved-import", "invalid-assignment"}}


def test_parses_violations_across_multiple_files(ty_boost: TyBoost) -> None:
    output = "src/foo.py:1:1: error[unresolved-import] ...\nsrc/bar.py:2:3: error[invalid-return-type] ...\n"
    result = ty_boost._parse_ty_output(output)  # noqa: SLF001
    assert ViolationLocation("src/foo.py", 1) in result
    assert ViolationLocation("src/bar.py", 2) in result


def test_ignores_non_matching_lines(ty_boost: TyBoost) -> None:
    output = "error: some fatal error without file info\nFound 1 error.\n"
    assert ty_boost._parse_ty_output(output) == {}  # noqa: SLF001


def test_empty_output_returns_empty(ty_boost: TyBoost) -> None:
    assert ty_boost._parse_ty_output("") == {}  # noqa: SLF001


# =============================================================================
# MERGE HELPER
# =============================================================================


def test_merge_adds_ignore_to_clean_line() -> None:
    result = _merge_ty_ignore(raw_line="x = foo()\n", codes={"unresolved-import"})
    assert result == "x = foo()  # ty: ignore[unresolved-import]\n"


def test_merge_preserves_eol() -> None:
    result = _merge_ty_ignore(raw_line="x = foo()\r\n", codes={"unresolved-import"})
    assert result.endswith("\r\n")


def test_merge_sorts_codes_alphabetically() -> None:
    result = _merge_ty_ignore(raw_line="x = foo()\n", codes={"unresolved-import", "invalid-assignment"})
    ia_pos = result.index("invalid-assignment")
    ui_pos = result.index("unresolved-import")
    assert ia_pos < ui_pos


def test_merge_merges_with_existing_ignore() -> None:
    result = _merge_ty_ignore(
        raw_line="x = foo()  # ty: ignore[invalid-assignment]\n",
        codes={"unresolved-import"},
    )
    assert "invalid-assignment" in result
    assert "unresolved-import" in result
    assert result.count("# ty: ignore") == 1


def test_merge_deduplicates_codes() -> None:
    result = _merge_ty_ignore(
        raw_line="x = foo()  # ty: ignore[unresolved-import]\n",
        codes={"unresolved-import"},
    )
    assert result.count("unresolved-import") == 1


def test_merge_handles_multi_code_existing_ignore() -> None:
    result = _merge_ty_ignore(
        raw_line="x = foo()  # ty: ignore[invalid-assignment, unresolved-import]\n",
        codes={"invalid-return-type"},
    )
    assert "invalid-assignment" in result
    assert "invalid-return-type" in result
    assert "unresolved-import" in result
    assert result.count("# ty: ignore") == 1


# =============================================================================
# APPLY IGNORES
# =============================================================================


def test_adds_ty_ignore_to_clean_line(mock_repo: RepositoryController, ty_boost: TyBoost) -> None:
    mock_repo.write_file("src/foo.py", "x = foo()\n")
    ty_boost._apply_ty_ignores({ViolationLocation("src/foo.py", 1): {"unresolved-import"}})  # noqa: SLF001
    assert "# ty: ignore[unresolved-import]" in (mock_repo.path / "src/foo.py").read_text()


def test_merges_with_existing_ty_ignore(mock_repo: RepositoryController, ty_boost: TyBoost) -> None:
    mock_repo.write_file("src/foo.py", "x = foo()  # ty: ignore[invalid-assignment]\n")
    ty_boost._apply_ty_ignores({ViolationLocation("src/foo.py", 1): {"unresolved-import"}})  # noqa: SLF001
    content = (mock_repo.path / "src/foo.py").read_text()
    assert "invalid-assignment" in content
    assert "unresolved-import" in content
    assert content.count("# ty: ignore") == 1


def test_handles_multiple_lines_in_same_file(mock_repo: RepositoryController, ty_boost: TyBoost) -> None:
    mock_repo.write_file("src/foo.py", "x = foo()\ny = bar()\n")
    ty_boost._apply_ty_ignores(  # noqa: SLF001
        {
            ViolationLocation("src/foo.py", 1): {"unresolved-import"},
            ViolationLocation("src/foo.py", 2): {"invalid-return-type"},
        }
    )
    lines = (mock_repo.path / "src/foo.py").read_text().splitlines()
    assert "# ty: ignore[unresolved-import]" in lines[0]
    assert "# ty: ignore[invalid-return-type]" in lines[1]


def test_skips_missing_file_without_raising(ty_boost: TyBoost) -> None:
    ty_boost._apply_ty_ignores({ViolationLocation("nonexistent.py", 1): {"unresolved-import"}})  # noqa: SLF001


def test_adds_ty_ignore_to_empty_file(mock_repo: RepositoryController, ty_boost: TyBoost) -> None:
    mock_repo.write_file("src/__init__.py", "")
    ty_boost._apply_ty_ignores({ViolationLocation("src/__init__.py", 1): {"missing-module-docstring"}})  # noqa: SLF001
    content = (mock_repo.path / "src/__init__.py").read_text()
    assert "# ty: ignore[missing-module-docstring]" in content


# =============================================================================
# APPLY
# =============================================================================


@pytest.mark.smoke
def test_apply_writes_ty_config_to_pyproject(mock_repo: RepositoryController, patched_ty_apply: PatchedTyApply) -> None:
    patched_ty_apply.boost.apply()
    content = (mock_repo.path / "pyproject.toml").read_text()
    assert "[tool.ty" in content
    assert "error-on-warning = true" in content


def test_apply_makes_configure_ty_commit(patched_ty_apply: PatchedTyApply) -> None:
    patched_ty_apply.boost.apply()
    messages = [c.args[0] for c in patched_ty_apply.mock_git.call_args_list]
    assert any("Configure ty" in m for m in messages)


def test_apply_stops_when_check_passes(patched_ty_apply: PatchedTyApply) -> None:
    patched_ty_apply.boost.apply()
    patched_ty_apply.mock_check.assert_called_once()


@pytest.mark.smoke
def test_apply_inserts_ty_ignore_on_violation(
    mock_repo: RepositoryController,
    patched_ty_apply: PatchedTyApply,
    fail_result: SubprocessResultFactory,
    ok_result: SubprocessResultFactory,
) -> None:
    mock_repo.write_file("src/foo.py", "x = foo()\n")
    patched_ty_apply.mock_check.side_effect = [
        fail_result("src/foo.py:1:1: error[unresolved-import] Cannot resolve import 'foo'\n"),
        ok_result(),
    ]
    patched_ty_apply.boost.apply()
    assert "# ty: ignore[unresolved-import]" in (mock_repo.path / "src/foo.py").read_text()


def test_apply_iterates_until_check_passes(
    mock_repo: RepositoryController,
    patched_ty_apply: PatchedTyApply,
    fail_result: SubprocessResultFactory,
    ok_result: SubprocessResultFactory,
) -> None:
    mock_repo.write_file("src/foo.py", "x = foo()\n")
    patched_ty_apply.mock_check.side_effect = [
        fail_result("src/foo.py:1:1: error[unresolved-import] ...\n"),
        fail_result("src/foo.py:1:1: error[invalid-assignment] ...\n"),
        ok_result(),
    ]
    patched_ty_apply.boost.apply()
    assert patched_ty_apply.mock_check.call_count == 3  # noqa: PLR2004


def test_apply_stops_after_max_iterations(
    mock_repo: RepositoryController,
    patched_ty_apply: PatchedTyApply,
    fail_result: SubprocessResultFactory,
) -> None:
    mock_repo.write_file("src/foo.py", "x = foo()\n")
    patched_ty_apply.mock_check.return_value = fail_result("src/foo.py:1:1: error[unresolved-import] ...\n")
    patched_ty_apply.boost.apply()
    assert patched_ty_apply.mock_check.call_count == _MAX_TY_ITERATIONS


def test_apply_stops_when_output_unparseable(
    patched_ty_apply: PatchedTyApply,
    fail_result: SubprocessResultFactory,
) -> None:
    patched_ty_apply.mock_check.return_value = fail_result("fatal: some config error\n")
    patched_ty_apply.boost.apply()
    patched_ty_apply.mock_check.assert_called_once()


# =============================================================================
# MISC
# =============================================================================


def test_commit_message(ty_boost: TyBoost) -> None:
    assert ty_boost.commit_message() == "✅ Silence ty violations"


def test_get_name() -> None:
    assert TyBoost.get_name() == "ty"
