"""Mypy boost implementation."""

import re
from typing import TYPE_CHECKING, Any, NamedTuple

from loguru import logger
from tomlkit import TOMLDocument, table

from pimp_my_repo.core.boosts.base import Boost, BoostSkippedError
from pimp_my_repo.core.boosts.ruff import RuffBoost
from pimp_my_repo.core.tools.pyproject import PyProjectNotFoundError

if TYPE_CHECKING:
    import subprocess

_MAX_MYPY_ITERATIONS = 7

# Supports both "path:line: error:" and "path:line:column: error:" (--show-column-numbers)
_MYPY_ERROR_RE = re.compile(
    r"^(?P<path>.+?):(?P<line>\d+)(?::\d+)?: error: .* \[(?P<code>[^\]]+)\]$",
)
# "note: Error code "X" not covered by "type: ignore" comment"
_MYPY_NOTE_UNCOVERED_RE = re.compile(
    r"^(?P<path>.+?):(?P<line>\d+)(?::\d+)?: note: Error code \"(?P<code>[^\"]+)\" not covered",
)
_TYPE_IGNORE_RE = re.compile(r"# type: ignore(?:\[([^\]]*)\])?")
# Parses which codes are unused from: Unused "type: ignore[X, Y]" comment  [unused-ignore]
_MYPY_UNUSED_IGNORE_RE = re.compile(r'Unused "type: ignore\[(?P<codes>[^\]]+)\]" comment\s+\[unused-ignore\]')


class ViolationLocation(NamedTuple):
    """A single violation location: file path and line number."""

    filepath: str
    lineno: int


type ErrorCodes = set[str]
type ViolationsByLocation = dict[ViolationLocation, ErrorCodes]
type LineViolations = dict[int, ErrorCodes]
type ViolationsByFile = dict[str, LineViolations]


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
                code = match.group("code")
                if code == "unused-ignore":
                    # Extract which specific codes are unused so we only remove those,
                    # leaving any codes that are still suppressing real errors intact.
                    unused_match = _MYPY_UNUSED_IGNORE_RE.search(line)
                    if unused_match:
                        for uc in unused_match.group("codes").split(","):
                            violations.setdefault(key, set()).add(f"!{uc.strip()}")
                    else:
                        violations.setdefault(key, set()).add("unused-ignore")
                else:
                    violations.setdefault(key, set()).add(code)
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
            codes_to_remove = {c[1:] for c in codes if c.startswith("!")}
            effective_codes = {c for c in codes if not c.startswith("!") and c != "unused-ignore"}
            if codes_to_remove:
                lines[idx] = _remove_type_ignore_codes(raw_line=lines[idx], codes=codes_to_remove)
            if effective_codes:
                lines[idx] = _merge_type_ignore(raw_line=lines[idx], codes=effective_codes)
            if not codes_to_remove and not effective_codes:
                # Bare unused-ignore with no parseable codes: remove the whole comment.
                lines[idx] = _remove_type_ignore(lines[idx])

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
        self._run_ruff()
        return True

    def _run_ruff(self) -> None:
        """Run ruff suppress iterations if ruff is configured in the repo."""
        data = self.pyproject.read()
        tool_section = data.get("tool")
        if not tool_section or "ruff" not in tool_section:
            return
        RuffBoost(tools=self.tools).run_suppress_iterations()

    def _add_dmypy_to_gitignore(self) -> None:
        """Ensure .dmypy.json is listed in .gitignore."""
        entry = ".dmypy.json"
        gitignore_path = self.repo_path / ".gitignore"
        if gitignore_path.exists():
            existing = gitignore_path.read_text(encoding="utf-8")
            if entry in existing:
                return
            separator = "" if existing.endswith("\n") else "\n"
            gitignore_path.write_text(f"{existing}{separator}{entry}\n", encoding="utf-8")
        else:
            gitignore_path.write_text(f"{entry}\n", encoding="utf-8")

    def _configure_mypy(self) -> None:
        self._add_mypy()
        logger.info("Configuring [tool.mypy] strict = true in pyproject.toml...")
        pyproject_data = self.pyproject.read()
        pyproject_data = self._ensure_mypy_config(pyproject_data)
        self.pyproject.write(pyproject_data)
        self._add_dmypy_to_gitignore()
        self.git.commit("🔧 Configure mypy with strict mode", no_verify=True)
        logger.info("Committed mypy configuration")

    def _add_mypy(self) -> None:
        self.uv.add_package("mypy", group="lint")

    def commit_message(self) -> str:
        """Generate commit message for Mypy boost."""
        return "✅ Silence mypy violations"


def _remove_type_ignore(raw_line: str) -> str:
    """Remove type: ignore from a line (for unused-ignore violations)."""
    line = raw_line.rstrip("\n").rstrip("\r")
    eol = raw_line[len(line) :]
    removed = _TYPE_IGNORE_RE.sub("", line).rstrip()
    if removed.endswith(","):
        removed = removed.rstrip(",").rstrip()
    return f"{removed}{eol}"


def _remove_type_ignore_codes(*, raw_line: str, codes: set[str]) -> str:
    """Remove specific codes from # type: ignore[...] on a line.

    If all codes in the bracket are removed, removes the whole comment.
    A bare # type: ignore (no codes) is left unchanged.
    """

    def replace_match(m: re.Match[str]) -> str:
        existing_str = m.group(1)
        if not existing_str:
            return m.group(0)  # bare type: ignore, leave as-is
        remaining = [c.strip() for c in existing_str.split(",") if c.strip() not in codes]
        if not remaining:
            return ""
        return f"# type: ignore[{', '.join(remaining)}]"

    line = raw_line.rstrip("\n").rstrip("\r")
    eol = raw_line[len(line) :]
    result = _TYPE_IGNORE_RE.sub(replace_match, line).rstrip()
    if result.endswith(","):
        result = result.rstrip(",").rstrip()
    return f"{result}{eol}"


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

    # Find the start of trailing comments. Check both "  # " (normal) and "  #:" (Sphinx doc
    # comments) so that type: ignore is placed before any inline comment, including #: style.
    idx_space = line.find("  # ")
    idx_colon = line.find("  #:")
    hash_idx = min((i for i in [idx_space, idx_colon] if i >= 0), default=-1)
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
    # Use re.sub to collapse only 3+ spaces (artifacts from removing the type: ignore token)
    # to exactly 2 spaces, leaving intentional double-space separators intact.
    remaining = re.sub(r" {3,}", "  ", _TYPE_IGNORE_RE.sub("", other_comments)).strip()
    if remaining.startswith(",") or remaining.endswith(","):
        remaining = remaining.strip(",").strip()
    other_part = f"  {remaining}" if remaining and remaining != "#" else ""

    return f"{prefix}  {type_ignore_part}{other_part}{eol}"
