"""Ruff boost implementation."""

import json
import re
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
# Matches no-qa annotations case-insensitively, with or without a colon.
# Handles: `# no-qa: F401`, `# NO-QA: F401`, `# NO-QA isort:skip`, bare `# no-qa`.
_NOQA_RE = re.compile(r"#\s*no-qa\b\s*:?\s*([^#\n]*)", re.IGNORECASE)
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

        violations = self._parse_violations(result.stdout)
        if not violations:
            logger.info("No parseable violations found; stopping")
            return False

        logger.info(f"Found {len(violations)} violations, applying noqa comments...")
        self._apply_noqa(violations)
        return True

    def commit_message(self) -> str:
        """Generate commit message for Ruff boost."""
        return "✅ Silence ruff violations"


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

    # Determine prefix (before any trailing comments).
    first_comment_start = len(line)
    if noqa_matches:
        first_comment_start = min(first_comment_start, noqa_matches[0].start())
    if type_match is not None:
        first_comment_start = min(first_comment_start, type_match.start())
    prefix = line[:first_comment_start].rstrip()

    # Collect ruff codes and non-ruff directives from ALL noqa matches.
    existing_ruff_codes: list[str] = []
    non_ruff_parts: list[str] = []
    for m in noqa_matches:
        raw_codes_str = m.group(1).strip()
        existing_ruff_codes.extend(_RUFF_CODE_RE.findall(raw_codes_str))
        leftover = _RUFF_CODE_RE.sub("", raw_codes_str).replace(",", " ")
        non_ruff_parts.extend(leftover.split())

    all_codes = sorted(set(existing_ruff_codes) | codes)
    noqa_part = f"# noqa: {', '.join(all_codes)}"

    # Non-ruff directives (e.g. isort:skip) become their own comment before noqa.
    non_ruff_comment = f"  # {' '.join(non_ruff_parts)}" if non_ruff_parts else ""

    # Preserve type: ignore if present (must come before noqa for mypy).
    type_ignore_part = ""
    if type_match is not None:
        type_ignore_part = f"  {line[type_match.start() : type_match.end()]}"

    return f"{prefix}{non_ruff_comment}{type_ignore_part}  {noqa_part}{eol}"
