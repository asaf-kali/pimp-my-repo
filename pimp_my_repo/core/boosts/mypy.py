"""Mypy boost implementation."""

import re
from typing import TYPE_CHECKING, Any, NamedTuple

from loguru import logger
from tomlkit import TOMLDocument, table

from pimp_my_repo.core.boosts.base import Boost, BoostSkippedError
from pimp_my_repo.core.tools.pyproject import PyProjectNotFoundError

if TYPE_CHECKING:
    import subprocess

_MAX_MYPY_ITERATIONS = 3

# Supports both "path:line: error:" and "path:line:column: error:" (--show-column-numbers)
_MYPY_ERROR_RE = re.compile(
    r"^(?P<path>.+?):(?P<line>\d+)(?::\d+)?: error: .* \[(?P<code>[^\]]+)\]$",
)
# "note: Error code "X" not covered by "type: ignore" comment"
_MYPY_NOTE_UNCOVERED_RE = re.compile(
    r"^(?P<path>.+?):(?P<line>\d+)(?::\d+)?: note: Error code \"(?P<code>[^\"]+)\" not covered",
)
_TYPE_IGNORE_RE = re.compile(r"# type: ignore(?:\[([^\]]*)\])?")


class ViolationLocation(NamedTuple):
    """A single violation location: file path and line number."""

    filepath: str
    lineno: int


type ErrorCodes = set[str]
type ViolationsByLocation = dict[ViolationLocation, ErrorCodes]
type LineViolations = dict[int, ErrorCodes]
type ViolationsByFile = dict[str, LineViolations]


def _remove_type_ignore(raw_line: str) -> str:
    """Remove type: ignore from a line (for unused-ignore violations)."""
    line = raw_line.rstrip("\n").rstrip("\r")
    eol = raw_line[len(line) :]
    removed = _TYPE_IGNORE_RE.sub("", line).rstrip()
    if removed.endswith(","):
        removed = removed.rstrip(",").rstrip()
    return f"{removed}{eol}"


def _merge_type_ignore(*, raw_line: str, codes: ErrorCodes) -> str:
    """Add or merge type: ignore[codes] into a source line.

    Mypy only recognizes type: ignore when it is the FIRST comment on a line
    (before any other # comment). Place it before noqa and any other trailing
    comments, merging all existing type: ignore comments into one.
    """
    line = raw_line.rstrip("\n").rstrip("\r")
    eol = raw_line[len(line) :]
    marker = "# type: ignore"

    # If we already ignore everything (bare type: ignore with no codes), keep as-is.
    if marker in line and "[" not in line.split(marker, maxsplit=1)[1]:
        return raw_line

    # Find the start of trailing comments. Use the first "  # " to split off the
    # comment block (e.g. "code  # type: ignore[...]  # noqa: X").
    hash_idx = line.find("  # ")
    if hash_idx >= 0:
        prefix = line[:hash_idx].rstrip()
        other_comments = line[hash_idx:].strip()
    elif '"' not in line and "'" not in line:
        # No quotes: safe to use first #
        hash_idx = line.find("#")
        if hash_idx >= 0:
            prefix = line[:hash_idx].rstrip()
            other_comments = line[hash_idx:].strip()
        else:
            prefix = line
            other_comments = ""
    else:
        prefix = line
        other_comments = ""

    # Extract and merge type: ignore codes from ALL type: ignore comments on the line.
    # Mypy only uses the first comment; multiple type: ignore must be merged into one.
    existing_codes: list[str] = []
    for type_match in _TYPE_IGNORE_RE.finditer(other_comments):
        if type_match.group(1):
            existing_codes.extend(c.strip() for c in type_match.group(1).split(",") if c.strip())
    all_codes = sorted(set(existing_codes) | codes)
    type_ignore_part = f"{marker}[{', '.join(all_codes)}]"

    # Rebuild other_comments without type: ignore, preserving noqa and other comments.
    remaining = _TYPE_IGNORE_RE.sub("", other_comments).replace("  ", " ").strip()
    if remaining.startswith(",") or remaining.endswith(","):
        remaining = remaining.strip(",").strip()
    other_part = f"  {remaining}" if remaining and remaining != "#" else ""

    return f"{prefix}  {type_ignore_part}{other_part}{eol}"


class MypyBoost(Boost):
    """Boost for integrating Mypy type checker in strict mode."""

    def apply(self) -> None:
        """Add mypy, configure strict mode, commit, then suppress all violations."""
        self._verify_preconditions()
        self._configure_mypy()
        self._apply_ignores()

    def _verify_preconditions(self) -> None:
        self._verify_uv_present()
        self._verify_pyproject_present()

    def _verify_uv_present(self) -> None:
        try:
            result = self.uv.run("--version", check=False)
            if result.returncode != 0:
                msg = "uv is not available"
                raise BoostSkippedError(msg)
        except (FileNotFoundError, OSError) as exc:
            msg = "uv is not installed"
            raise BoostSkippedError(msg) from exc

    def _verify_pyproject_present(self) -> None:
        try:
            self.pyproject.verify_present()
        except PyProjectNotFoundError as exc:
            msg = "No pyproject.toml found"
            raise BoostSkippedError(msg) from exc

    def _run_mypy(self) -> subprocess.CompletedProcess[str]:
        return self.uv.run("run", "mypy", ".", check=False)

    def _ensure_mypy_config(self, data: TOMLDocument) -> TOMLDocument:
        if "tool" not in data:
            data["tool"] = table()
        tool_section: Any = data["tool"]
        if "mypy" not in tool_section:
            tool_section["mypy"] = table()
        mypy_section: Any = tool_section["mypy"]
        mypy_section["strict"] = True
        return data

    def _parse_violations(self, output: str) -> ViolationsByLocation:
        """Parse mypy output into {ViolationLocation: {error_codes}}.

        Handles both error lines and "note: Error code not covered" lines,
        and supports optional column numbers in the output format.
        """
        violations: ViolationsByLocation = {}
        for raw_line in output.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            match = _MYPY_ERROR_RE.match(line)
            if match:
                key = ViolationLocation(filepath=match.group("path"), lineno=int(match.group("line")))
                violations.setdefault(key, set()).add(match.group("code"))
                continue
            match = _MYPY_NOTE_UNCOVERED_RE.match(line)
            if match:
                key = ViolationLocation(filepath=match.group("path"), lineno=int(match.group("line")))
                violations.setdefault(key, set()).add(match.group("code"))
        return violations

    def _apply_type_ignores(self, violations: ViolationsByLocation) -> None:
        """Insert or merge # type: ignore[codes] on each violating line."""
        by_file: ViolationsByFile = {}
        for location, codes in violations.items():
            by_file.setdefault(location.filepath, {})[location.lineno] = codes

        for filepath, line_violations in by_file.items():
            self._apply_type_ignores_to_file(filepath=filepath, line_violations=line_violations)

    def _apply_type_ignores_to_file(self, *, filepath: str, line_violations: LineViolations) -> None:
        full_path = self.repo_path / filepath
        if not full_path.exists():
            logger.warning(f"File not found, skipping: {full_path}")
            return

        lines = full_path.read_text(encoding="utf-8").splitlines(keepends=True)
        for lineno, codes in sorted(line_violations.items()):
            idx = lineno - 1
            if idx >= len(lines):
                continue
            # unused-ignore means the existing type: ignore is stale; strip it.
            # Other codes on the same line still apply normally.
            effective_codes = codes - {"unused-ignore"}
            if not effective_codes:
                lines[idx] = _remove_type_ignore(lines[idx])
            else:
                lines[idx] = _merge_type_ignore(raw_line=lines[idx], codes=effective_codes)

        full_path.write_text("".join(lines), encoding="utf-8")

    def _apply_ignores(self) -> None:
        for iteration in range(1, _MAX_MYPY_ITERATIONS + 1):
            if not self._process_mypy_iteration(iteration):
                break

    def _process_mypy_iteration(self, iteration: int) -> bool:
        """Run mypy and apply ignores for one iteration. Returns True if should continue."""
        logger.info(f"Running mypy (iteration {iteration}/{_MAX_MYPY_ITERATIONS})...")
        result = self._run_mypy()

        if result.returncode == 0:
            logger.info("mypy passed with no errors")
            return False

        violations = self._parse_violations(result.stdout + result.stderr)
        if not violations:
            logger.info("No parseable violations found; stopping")
            return False

        logger.info(f"Found {len(violations)} violations, applying type: ignore comments...")
        self._apply_type_ignores(violations)
        self.git.commit("✅ Silence mypy violations", no_verify=True)
        return True

    def _configure_mypy(self) -> None:
        self._add_mypy()
        logger.info("Configuring [tool.mypy] strict = true in pyproject.toml...")
        pyproject_data = self.pyproject.read()
        pyproject_data = self._ensure_mypy_config(pyproject_data)
        self.pyproject.write(pyproject_data)
        self.git.commit("🔧 Configure mypy with strict mode", no_verify=True)
        logger.info("Committed mypy configuration")

    def _add_mypy(self) -> None:
        self.uv.add_package("mypy", group="lint")

    def commit_message(self) -> str:
        """Generate commit message for Mypy boost."""
        return "✅ Silence mypy violations"
