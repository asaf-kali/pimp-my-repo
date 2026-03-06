"""Ruff boost implementation."""

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

from loguru import logger
from tomlkit import TOMLDocument, table

from pimp_my_repo.core.boosts.base import Boost, BoostSkippedError
from pimp_my_repo.core.tools.pyproject import PyProjectNotFoundError

if TYPE_CHECKING:
    import subprocess

_MAX_RUFF_ITERATIONS = 7

# Rules that must never be suppressed via noqa:
# - ERA001: treats the noqa comment itself as commented-out code → oscillation loop.
#   Instead, ERA001 is added to ruff's ignore list in the config.
_UNSUPPRESSIBLE_CODES: frozenset[str] = frozenset({"ERA001"})


class ViolationLocation(NamedTuple):
    """A single violation location: file path and line number."""

    filepath: str
    lineno: int


type ErrorCodes = set[str]
type ViolationsByLocation = dict[ViolationLocation, ErrorCodes]
type LineViolations = dict[int, ErrorCodes]
type ViolationsByFile = dict[str, LineViolations]

# To avoid this project's ruff confusion, we will address the noqa comments as no-qa.
# Matches no-qa annotations case-insensitively, with or without a colon, with optional dash.
# Handles: `# no-qa: F401`, `# no-qa: F401`, `# NO-QA isort:skip`, bare `# no-qa`.
_NOQA_RE = re.compile(r"#\s*noqa\b\s*:?\s*([^#\n]*)", re.IGNORECASE)
# Matches valid ruff rule codes: 1-4 uppercase letters followed by digits.
_RUFF_CODE_RE = re.compile(r"\b([A-Z]{1,4}\d+)\b")
_TYPE_IGNORE_RE = re.compile(r"# type: ignore(?:\[([^\]]*)\])?")


class RuffBoost(Boost):
    """Boost for integrating Ruff linter and formatter."""

    def apply(self) -> None:
        """Add ruff, configure it, auto-format, then suppress all check violations."""
        self._verify_uv_present()
        self._verify_pyproject_present()

        self.uv.add_package("ruff", group="lint")

        logger.info("Configuring [tool.ruff.lint] select = ['ALL'] in pyproject.toml...")
        pyproject_data = self.pyproject.read()
        pyproject_data = self._ensure_ruff_config(pyproject_data)
        self.pyproject.write(pyproject_data)

        self.git.commit("🔧 Configure ruff", no_verify=True)

        logger.info("Running ruff format...")
        self._run_ruff_format()
        self.run_suppress_iterations()

    def commit_message(self) -> str:
        """Generate commit message for Ruff boost."""
        return "✅ Silence ruff violations"

    def run_suppress_iterations(self) -> None:
        """Run ruff check + noqa suppression iterations, re-formatting after each.

        Called by other boosts after modifying files, to restore ruff stability.
        """
        for iteration in range(1, _MAX_RUFF_ITERATIONS + 1):
            if not self._suppress_violations_iteration(iteration=iteration):
                break
            # Re-format after noqa additions: adding inline comments can shift
            # formatter decisions (e.g. magic trailing comma, line wrapping).
            self._run_ruff_format()

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

    def _run_ruff_format(self) -> subprocess.CompletedProcess[str]:
        return self.uv.run("run", "ruff", "format", ".", check=False)

    def _run_ruff_check(self) -> subprocess.CompletedProcess[str]:
        return self.uv.run("run", "ruff", "check", ".", "--output-format=json", check=False)

    def _ensure_ruff_config(self, data: TOMLDocument) -> TOMLDocument:
        if "tool" not in data:
            data["tool"] = table()
        tool_section: Any = data["tool"]
        if "ruff" not in tool_section:
            tool_section["ruff"] = table()
        ruff_section: Any = tool_section["ruff"]
        ruff_section["line-length"] = 120
        if "lint" not in ruff_section:
            ruff_section["lint"] = table()
        lint_section: Any = ruff_section["lint"]
        lint_section["select"] = ["ALL"]
        # ERA001: adding `# no-qa: ERA001` itself gets flagged as commented-out code.
        # COM812, ISC001: conflict with ruff formatter, causing format/check oscillation.
        # D203, D212: incompatible with D211/D213 (ruff picks one but warns; be explicit).
        lint_section["ignore"] = ["ERA001", "COM812", "ISC001", "D203", "D212"]
        return data

    def _parse_violations(self, output: str) -> ViolationsByLocation:
        """Parse ruff JSON output into {ViolationLocation: {rule_codes}}, using noqa_row."""
        violations: ViolationsByLocation = {}
        try:
            raw_violations = json.loads(output)
        except (json.JSONDecodeError, ValueError):  # fmt: off
            logger.warning("Failed to parse ruff JSON output")
            return violations

        for raw in raw_violations:
            code: str = raw.get("code", "")
            if code in _UNSUPPRESSIBLE_CODES:
                continue
            noqa_row: int | None = raw.get("noqa_row")
            if noqa_row is None:
                continue
            key = ViolationLocation(filepath=raw["filename"], lineno=noqa_row)
            violations.setdefault(key, set()).add(code)

        return violations

    def _apply_noqa(self, violations: ViolationsByLocation) -> None:
        """Insert or merge # noqa: CODES on each violating line."""
        by_file: ViolationsByFile = {}
        for location, codes in violations.items():
            by_file.setdefault(location.filepath, {})[location.lineno] = codes

        for filepath, line_violations in by_file.items():
            self._apply_noqa_to_file(filepath=filepath, line_violations=line_violations)

    def _apply_noqa_to_file(self, *, filepath: str, line_violations: LineViolations) -> None:
        full_path = self.repo_path / filepath
        if not full_path.exists():
            logger.warning(f"File not found, skipping: {full_path}")
            return

        lines = full_path.read_text(encoding="utf-8").splitlines(keepends=True)
        for lineno, codes in sorted(line_violations.items()):
            idx = lineno - 1
            if idx < 0:
                continue
            if idx >= len(lines):
                # File is shorter than expected (e.g. an empty __init__.py);
                # prepend a noqa comment so ruff can see the suppression.
                lines.insert(0, f"# noqa: {', '.join(sorted(codes))}\n")
            else:
                lines[idx] = _merge_noqa(raw_line=lines[idx], codes=codes)

        full_path.write_text("".join(lines), encoding="utf-8")

    def _suppress_violations_iteration(self, *, iteration: int) -> bool:
        """Run one ruff-check-then-noqa cycle. Returns True if another iteration is needed."""
        logger.info(f"Running ruff check (iteration {iteration}/{_MAX_RUFF_ITERATIONS})...")
        result = self._run_ruff_check()

        if result.returncode == 0:
            logger.info("ruff check passed with no violations")
            return False

        excluded = self._exclude_syntax_error_files(result.stdout)
        violations = self._parse_violations(result.stdout)
        if not violations and not excluded:
            logger.info("No parseable violations found; stopping")
            return False

        if violations:
            logger.info(f"Found {len(violations)} violations, applying noqa comments...")
            self._apply_noqa(violations)
        return True

    def _parse_syntax_error_files(self, output: str) -> set[str]:
        """Extract relative paths of files with syntax errors from ruff JSON output."""
        files: set[str] = set()
        try:
            raw_violations = json.loads(output)
        except (json.JSONDecodeError, ValueError):  # fmt: off
            return files
        for v in raw_violations:
            if v.get("code") != "invalid-syntax":
                continue
            abs_path = v.get("filename", "")
            try:
                rel_path = str(Path(abs_path).relative_to(self.repo_path))
            except ValueError:
                rel_path = abs_path
            files.add(rel_path)
        return files

    def _exclude_syntax_error_files(self, output: str) -> bool:
        """Add files with syntax errors to [tool.ruff.exclude]. Returns True if any added."""
        files = self._parse_syntax_error_files(output)
        if not files:
            return False
        logger.info(f"Excluding {len(files)} file(s) with syntax errors from ruff: {files}")
        self._add_ruff_excludes(files)
        return True

    def _add_ruff_excludes(self, files: set[str]) -> None:
        """Append files to [tool.ruff.extend-exclude] in pyproject.toml."""
        data = self.pyproject.read()
        tool_section: Any = data["tool"]
        ruff_section: Any = tool_section["ruff"]
        existing: set[str] = set(ruff_section.get("extend-exclude") or set())
        new_excludes = existing | files
        if new_excludes == existing:
            return
        ordered = sorted(new_excludes)
        ruff_section["extend-exclude"] = ordered
        self.pyproject.write(data)


def _merge_noqa(*, raw_line: str, codes: ErrorCodes) -> str:
    """Merge noqa codes into a source line.

    Handles all noqa variants (case-insensitive, with or without colon) and
    non-ruff directives like ``isort:skip``. All noqa comments on the line are
    merged into a single canonical ``# noqa: CODE1, CODE2``. Non-ruff content
    is preserved as a separate leading comment so tools like isort still see it.
    ``# type: ignore`` is placed before ``# noqa`` as mypy requires.
    """
    line = raw_line.rstrip("\n").rstrip("\r")
    eol = raw_line[len(line) :]

    noqa_matches = list(_NOQA_RE.finditer(line))
    type_match = _TYPE_IGNORE_RE.search(line)

    # Split line into code and comment section at the first recognized comment.
    first_comment = len(line)
    if noqa_matches:
        first_comment = min(first_comment, noqa_matches[0].start())
    if type_match is not None:
        first_comment = min(first_comment, type_match.start())
    code = line[:first_comment].rstrip()
    comment_section = line[first_comment:]

    # Parse noqa annotations: collect ruff codes and non-ruff directives (e.g. isort:skip).
    existing_ruff_codes: list[str] = []
    non_ruff_parts: list[str] = []
    for m in noqa_matches:
        raw = m.group(1).strip()
        existing_ruff_codes.extend(_RUFF_CODE_RE.findall(raw))
        leftover = _RUFF_CODE_RE.sub("", raw).replace(",", " ")
        non_ruff_parts.extend(leftover.split())

    # Remove noqa annotations from comment section, keeping type: ignore and other comments.
    previous_comments = re.sub(r" {2,}", "  ", _NOQA_RE.sub("", comment_section)).strip()
    # Non-ruff directives (e.g. isort:skip) go in their own comment before noqa.
    if non_ruff_parts:
        non_ruff = f"# {' '.join(non_ruff_parts)}"
        previous_comments = f"{non_ruff}  {previous_comments}" if previous_comments else non_ruff

    # Build new noqa and reconstruct with noqa at the end.
    all_codes = sorted(set(existing_ruff_codes) | codes)
    new_noqa = f"# noqa: {', '.join(all_codes)}"
    if previous_comments:
        return f"{code}  {previous_comments}  {new_noqa}{eol}"
    return f"{code}  {new_noqa}{eol}"
