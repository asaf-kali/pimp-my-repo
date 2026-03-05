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

_MAX_RUFF_ITERATIONS = 3

# Rules that must never be suppressed via noqa:
# - ERA001: treats the noqa comment itself as commented-out code → oscillation loop.
_UNSUPPRESSIBLE_CODES: frozenset[str] = frozenset({"ERA001"})


class ViolationLocation(NamedTuple):
    """A single violation location: file path and line number."""

    filepath: str
    lineno: int


type ErrorCodes = set[str]
type ViolationsByLocation = dict[ViolationLocation, ErrorCodes]
type LineViolations = dict[int, ErrorCodes]
type ViolationsByFile = dict[str, LineViolations]


_NOQA_RE = re.compile(r"# noqa:([^#\n]*)")
_TYPE_IGNORE_RE = re.compile(r"# type: ignore(?:\[([^\]]*)\])?")


def _merge_noqa(*, raw_line: str, codes: ErrorCodes) -> str:
    """Merge noqa codes into a source line, preserving type: ignore before noqa."""
    line = raw_line.rstrip("\n").rstrip("\r")
    eol = raw_line[len(line) :]

    noqa_match = _NOQA_RE.search(line)
    type_match = _TYPE_IGNORE_RE.search(line)

    # Determine prefix (before any trailing comments).
    first_comment_start = len(line)
    if noqa_match is not None:
        first_comment_start = min(first_comment_start, noqa_match.start())
    if type_match is not None:
        first_comment_start = min(first_comment_start, type_match.start())
    prefix = line[:first_comment_start].rstrip()

    # Merge noqa codes.
    existing_noqa: list[str] = []
    if noqa_match is not None:
        existing_noqa = [c.strip() for c in noqa_match.group(1).split(",") if c.strip()]
    all_codes = sorted(set(existing_noqa) | codes)
    noqa_part = f"# noqa: {', '.join(all_codes)}"

    # Preserve type: ignore if present (must come before noqa for mypy).
    type_ignore_part = ""
    if type_match is not None:
        type_ignore_part = f"  {line[type_match.start() : type_match.end()]}"

    return f"{prefix}{type_ignore_part}  {noqa_part}{eol}"


class RuffBoost(Boost):
    """Boost for integrating Ruff linter and formatter."""

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
            if idx >= len(lines):
                continue
            lines[idx] = _merge_noqa(raw_line=lines[idx], codes=codes)

        full_path.write_text("".join(lines), encoding="utf-8")

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
        self._run_ruff_format()
        self._run_ruff_format()
        self.git.commit("🎨 Auto-format with ruff", no_verify=True)

        for iteration in range(1, _MAX_RUFF_ITERATIONS + 1):
            if not self._suppress_violations_iteration(iteration=iteration):
                break

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
        self.git.commit("✅ Silence ruff violations", no_verify=True)
        return True

    def commit_message(self) -> str:
        """Generate commit message for Ruff boost."""
        return "✅ Silence ruff violations"
