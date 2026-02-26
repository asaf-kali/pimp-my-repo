"""Ruff boost implementation."""

import re
from typing import TYPE_CHECKING, Any, NamedTuple

from loguru import logger
from tomlkit import TOMLDocument, table

from pimp_my_repo.core.boosts.base import Boost

if TYPE_CHECKING:
    import subprocess

_MAX_RUFF_ITERATIONS = 3


class ViolationLocation(NamedTuple):
    """A single violation location: file path and line number."""

    filepath: str
    lineno: int


type ErrorCodes = set[str]
type ViolationsByLocation = dict[ViolationLocation, ErrorCodes]
type LineViolations = dict[int, ErrorCodes]
type ViolationsByFile = dict[str, LineViolations]


def _merge_noqa(*, raw_line: str, codes: ErrorCodes) -> str:
    """Merge noqa codes into a source line, preserving or creating the comment."""
    line = raw_line.rstrip("\n").rstrip("\r")
    eol = raw_line[len(line) :]

    noqa_match = re.search(r"#\s*noqa(?::\s*([A-Z0-9,\s]+))?", line)
    if not noqa_match:
        return f"{line}  # noqa: {', '.join(sorted(codes))}{eol}"

    existing_str = noqa_match.group(1) or ""
    existing = {c.strip() for c in existing_str.split(",") if c.strip()}
    all_codes = existing | codes
    new_noqa = f"# noqa: {', '.join(sorted(all_codes))}"
    merged = re.sub(r"#\s*noqa(?::\s*[A-Z0-9,\s]+)?", new_noqa, line).rstrip()
    return f"{merged}{eol}"


class RuffBoost(Boost):
    """Boost for integrating Ruff linter and formatter."""

    def _has_uncommitted_changes(self) -> bool:
        result = self.tools.git.status(porcelain=True)
        return bool(result.stdout.strip())

    def _commit_if_changes(self, message: str) -> None:
        """Stage all changes and commit only if there is something to commit."""
        self.tools.git.add()
        if self._has_uncommitted_changes():
            self.tools.git.commit(message, no_verify=True)
        else:
            logger.debug(f"Nothing to commit for: {message!r}")

    def _run_ruff_format(self) -> subprocess.CompletedProcess[str]:
        return self.tools.uv.run("run", "ruff", "format", ".", check=False)

    def _run_ruff_check(self) -> subprocess.CompletedProcess[str]:
        return self.tools.uv.run("run", "ruff", "check", ".", check=False)

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
        """Parse ruff check output into {ViolationLocation: {rule_codes}}."""
        violations: ViolationsByLocation = {}
        for line in output.splitlines():
            match = re.match(r"^(.+?):(\d+):\d+:\s+([A-Z][A-Z0-9]+)\s", line)
            if not match:
                continue
            key = ViolationLocation(filepath=match.group(1), lineno=int(match.group(2)))
            violations.setdefault(key, set()).add(match.group(3))
        return violations

    def _apply_noqa(self, violations: ViolationsByLocation) -> None:
        """Insert or merge # noqa: CODES on each violating line."""
        by_file: ViolationsByFile = {}
        for location, codes in violations.items():
            by_file.setdefault(location.filepath, {})[location.lineno] = codes

        for filepath, line_violations in by_file.items():
            self._apply_noqa_to_file(filepath=filepath, line_violations=line_violations)

    def _apply_noqa_to_file(self, *, filepath: str, line_violations: LineViolations) -> None:
        full_path = self.tools.repo_path / filepath
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
        self.tools.uv.verify_present()
        self.tools.pyproject.verify_present()

        # Phase 1: add dep + configure
        self.tools.uv.add_package("ruff", group="lint")

        logger.info("Configuring [tool.ruff.lint] select = ['ALL'] in pyproject.toml...")
        pyproject_data = self.tools.pyproject.read()
        pyproject_data = self._ensure_ruff_config(pyproject_data)
        self.tools.pyproject.write(pyproject_data)

        self._commit_if_changes("🔧 Configure ruff")

        # Phase 2: auto-format
        logger.info("Running ruff format...")
        self._run_ruff_format()
        self._commit_if_changes("🎨 Auto-format with ruff")

        # Phase 3: suppress check violations
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

        violations = self._parse_violations(result.stdout + result.stderr)
        if not violations:
            logger.info("No parseable violations found; stopping")
            return False

        logger.info(f"Found {len(violations)} violations, applying noqa comments...")
        self._apply_noqa(violations)
        self._commit_if_changes("✅ Silence ruff violations")
        return True

    def commit_message(self) -> str:
        """Generate commit message for Ruff boost."""
        return "✅ Silence ruff violations"
