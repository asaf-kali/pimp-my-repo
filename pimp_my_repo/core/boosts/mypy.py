"""Mypy boost implementation."""

import re
from pathlib import Path
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
# Matches any "error:" line regardless of whether it has a [code] suffix
_MYPY_ANY_ERROR_RE = re.compile(r"^(?P<path>.+?)(?::\d+(?::\d+)?)?: error: ")
# "Source file found twice" errors must exclude the parent directory, not just the file,
# because mypy's exclude option doesn't prevent discovery-stage errors on specific files.
_MYPY_FOUND_TWICE_RE = re.compile(r"Source file found twice under different module names")


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
        # Reverse order: inserting lines for triple-quote fixes shifts later indices,
        # but those are already processed when iterating highest-to-lowest.
        for lineno, codes in sorted(line_violations.items(), reverse=True):
            idx = lineno - 1
            if idx >= len(lines):
                continue
            codes_to_remove = {c[1:] for c in codes if c.startswith("!")}
            effective_codes = {c for c in codes if not c.startswith("!") and c != "unused-ignore"}
            if codes_to_remove:
                lines[idx] = _remove_type_ignore_codes(raw_line=lines[idx], codes=codes_to_remove)
            if effective_codes:
                _place_type_ignore(lines=lines, idx=idx, codes=effective_codes)
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

        syntax_files = {loc.filepath for loc, codes in violations.items() if "syntax" in codes}
        if syntax_files:
            self._exclude_mypy_files(syntax_files)
            violations = {loc: codes for loc, codes in violations.items() if loc.filepath not in syntax_files}

        output = result.stdout + result.stderr
        uncoded_files = self._exclude_blocking_uncoded_errors(output)

        if not violations and not syntax_files and not uncoded_files:
            logger.info("No parseable violations found; stopping")
            return False

        if violations:
            logger.info(f"Found {len(violations)} violations, applying type: ignore comments...")
            self._apply_type_ignores(violations)
            self._run_ruff()
        return True

    def _exclude_mypy_files(self, files: set[str]) -> None:
        """Add files to [tool.mypy] exclude list in pyproject.toml (as regex patterns)."""
        logger.info(f"Excluding {len(files)} file(s) with syntax errors from mypy: {files}")
        data = self.pyproject.read()
        tool_section: Any = data["tool"]
        mypy_section: Any = tool_section["mypy"]
        existing: set[str] = set(mypy_section.get("exclude", []))
        new_excludes = existing | {re.escape(f) for f in files}
        if new_excludes == existing:
            return
        mypy_section["exclude"] = sorted(new_excludes)
        self.pyproject.write(data)

    def _exclude_blocking_uncoded_errors(self, output: str) -> set[str]:
        """Exclude files with no-code blocking errors. Returns the excluded file set."""
        if "errors prevented further checking" not in output:
            return set()
        files = self._parse_uncoded_error_files(output)
        if files:
            self._exclude_mypy_files(files)
        return files

    def _parse_uncoded_error_files(self, output: str) -> set[str]:
        """Extract files/dirs with mypy errors that have no [code] (can't be suppressed inline).

        For "source file found twice" errors, returns the parent directory (with trailing slash)
        because mypy's exclude cannot prevent file-discovery errors for a specific file path.
        """
        files: set[str] = set()
        for line in output.splitlines():
            if ": error: " not in line:
                continue
            if _MYPY_ERROR_RE.match(line):
                continue  # has a [code]; handled by _parse_violations
            m = _MYPY_ANY_ERROR_RE.match(line)
            if not m:
                continue
            filepath = m.group("path")
            if _MYPY_FOUND_TWICE_RE.search(line):
                filepath = str(Path(filepath).parent) + "/"
            files.add(filepath)
        return files

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


def _find_unclosed_triple_quote_pos(line: str) -> tuple[int, str] | None:
    """Return (position, triple_quote) of the first unclosed triple-quote opener in line.

    Scans left-to-right, pairing openers with closers. If the last opener has no closer
    on the same line, returns its position so we can place the comment before it.
    """
    stripped = line.rstrip("\n").rstrip("\r")
    i = 0
    while i < len(stripped):
        ch = stripped[i]
        if ch in ('"', "'"):
            triple_quote = ch * 3
            if stripped[i : i + 3] == triple_quote:
                closer = stripped.find(triple_quote, i + 3)
                if closer == -1:
                    return (i, triple_quote)
                i = closer + 3
                continue
        i += 1
    return None


def _find_closing_triple_quote(*, lines: list[str], start_idx: int, quote: str) -> int | None:
    """Return the index of the first line that contains the closing triple-quote."""
    for i in range(start_idx, len(lines)):
        if quote in lines[i]:
            return i
    return None


def _place_type_ignore(*, lines: list[str], idx: int, codes: ErrorCodes) -> None:
    """Apply type: ignore to lines[idx], handling triple-quoted string openings.

    If the line opens an unclosed triple-quoted string, placing a comment after the
    opening triple-quote would embed it inside the string where mypy cannot see it.
    Instead, the comment is placed before the triple-quote by splitting the line.
    The caller must process violations in reverse line order so that any inserted
    lines do not shift the indices of not-yet-processed earlier violations.
    """
    raw_line = lines[idx]
    result = _find_unclosed_triple_quote_pos(raw_line)
    if result is None:
        lines[idx] = _merge_type_ignore(raw_line=raw_line, codes=codes)
        return

    triple_quote_pos, triple_quote = result
    line = raw_line.rstrip("\n").rstrip("\r")
    eol = raw_line[len(line) :]

    code_part = line[:triple_quote_pos]
    string_part = line[triple_quote_pos:]
    indent = len(line) - len(line.lstrip())
    type_ignore = f"# type: ignore[{', '.join(sorted(codes))}]"

    if code_part.rstrip().endswith("("):
        # Function call: place comment after (, move triple-quote to next line.
        lines[idx] = f"{code_part.rstrip()}  {type_ignore}{eol}"
        lines.insert(idx + 1, f"{' ' * (indent + 4)}{string_part.lstrip()}{eol}")
    else:
        # Assignment or other expression: wrap the RHS with () so the comment applies.
        # Find the closing triple-quote BEFORE inserting (indices shift after insert).
        closing_idx = _find_closing_triple_quote(lines=lines, start_idx=idx + 1, quote=triple_quote)
        if closing_idx is not None:
            closing_raw = lines[closing_idx]
            closing_line = closing_raw.rstrip("\n").rstrip("\r")
            closing_eol = closing_raw[len(closing_line) :]
            close_pos = closing_line.find(triple_quote) + len(triple_quote)
            lines[closing_idx] = f"{closing_line[:close_pos]}){closing_line[close_pos:]}{closing_eol}"
        lines[idx] = f"{code_part.rstrip()} (  {type_ignore}{eol}"
        lines.insert(idx + 1, f"{' ' * (indent + 4)}{string_part.lstrip()}{eol}")


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

    # If already a bare type: ignore (no codes), it suppresses everything; keep as-is.
    if marker in line and not line.split(marker, maxsplit=1)[1].startswith("["):
        return raw_line

    # Split line into code and comment section.
    # Check both "  # " and "  #:" (Sphinx doc comments) — take whichever comes first
    # so that type: ignore is placed before any inline comment, including #: style.
    idx_space = line.find("  # ")
    idx_colon = line.find("  #:")
    comment_start = min((i for i in [idx_space, idx_colon] if i >= 0), default=-1)
    if comment_start >= 0:
        code = line[:comment_start].rstrip()
        comment_section = line[comment_start:].strip()
    elif '"' not in line and "'" not in line:
        hash_idx = line.find("#")
        code = line[:hash_idx].rstrip() if hash_idx >= 0 else line
        comment_section = line[hash_idx:].strip() if hash_idx >= 0 else ""
    else:
        code = line
        comment_section = ""

    # Extract all existing type: ignore codes from the comment section.
    # Mypy only uses the first; merge all into one unified comment.
    existing_codes: list[str] = []
    for m in _TYPE_IGNORE_RE.finditer(comment_section):
        if m.group(1):
            existing_codes.extend(c.strip() for c in m.group(1).split(",") if c.strip())
    all_codes = sorted(set(existing_codes) | codes)
    new_type_ignore = f"{marker}[{', '.join(all_codes)}]"

    # Remove type: ignore from comment section, keeping noqa and other comments.
    # Collapse only 3+ spaces (artifacts of removal) to preserve intentional double-space gaps.
    remaining = re.sub(r" {3,}", "  ", _TYPE_IGNORE_RE.sub("", comment_section)).strip()
    if remaining.startswith(",") or remaining.endswith(","):
        remaining = remaining.strip(",").strip()

    # Reconstruct with type: ignore FIRST, then remaining comments (noqa etc.) after.
    if remaining and remaining != "#":
        return f"{code}  {new_type_ignore}  {remaining}{eol}"
    return f"{code}  {new_type_ignore}{eol}"
