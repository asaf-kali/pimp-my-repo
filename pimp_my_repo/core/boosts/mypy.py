"""Mypy boost implementation."""

import abc
import re
import shutil
from abc import abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

from loguru import logger
from tomlkit import TOMLDocument, table

from pimp_my_repo.core.boosts.base import Boost, BoostSkippedError
from pimp_my_repo.core.boosts.ruff import RuffBoost
from pimp_my_repo.core.tools.pyproject import PyProjectNotFoundError

if TYPE_CHECKING:
    import subprocess

_MAX_MYPY_ITERATIONS = 10

# Supports both "path:line: error:" and "path:line:column: error:" (--show-column-numbers).
# No $ anchor: allows trailing text after [code] that appears when pretty=true wraps
# the output and the summary line gets joined onto the last error line.
# Greedy .* before \[code\] ensures we match the LAST [code] in the line.
_MYPY_ERROR_RE = re.compile(
    r"^(?P<path>.+?):(?P<line>\d+)(?::\d+)?: error: .*\[(?P<code>[^\]]+)\]",
)
# Detects lines that start a new mypy diagnostic (path:line: or path:line:col:).
# Used to distinguish error header lines from pretty=true continuation/context lines.
_MYPY_LINE_START_RE = re.compile(r"^\S[^:]*:\d+(?::\d+)?: ")
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
# Directories with hyphens (e.g. "fonts-standard") are invalid Python package names.
# Mypy outputs these as fatal errors with no file/line context.
_MYPY_INVALID_PKG_NAME_RE = re.compile(r"^(\S+) is not a valid Python package name$", re.MULTILINE)


def _normalize_mypy_output(output: str) -> str:
    """Normalize mypy output to one logical line per diagnostic.

    With ``pretty = true``, mypy wraps long error lines across multiple lines
    and adds indented source-context and caret lines below each error.  This
    function reassembles wrapped lines into a single line and discards the
    indented context lines so that all downstream regex parsers see a uniform
    ``path:line: error: message [code]`` format.
    """
    result: list[str] = []
    for line in output.splitlines():
        if not line or line[0] in (" ", "\t"):
            continue  # skip empty lines and indented context / caret lines
        if result and not _MYPY_LINE_START_RE.match(line):
            result[-1] = result[-1] + " " + line.strip()
        else:
            result.append(line)
    return "\n".join(result)


class ViolationLocation(NamedTuple):
    file_path: str
    line_number: int


class TripleQuotePos(NamedTuple):
    position: int
    quote: str


type ErrorCodes = set[str]
type ViolationsByLocation = dict[ViolationLocation, ErrorCodes]
type LineViolations = dict[int, ErrorCodes]
type ViolationsByFile = dict[str, LineViolations]


class SyntaxHandlingResult(NamedTuple):
    violations: ViolationsByLocation
    newly_excluded: bool


class BaseMypyBoost(Boost, abc.ABC):
    """Abstract base for mypy-based boosts. Subclasses supply the type-checker runner."""

    def apply(self) -> None:
        """Add mypy, configure strict mode, commit, then suppress all violations."""
        self._verify_preconditions()
        self._configure_mypy()
        self._apply_ignores()

    @abstractmethod
    def _run_type_checker(self) -> subprocess.CompletedProcess[str]:
        """Run the type checker and return its result."""

    def _configure_extras(self) -> None:
        """Override to add subclass-specific setup steps inside _configure_mypy."""

    def _verify_preconditions(self) -> None:
        self._verify_uv_present()
        self._verify_pyproject_present()

    def _verify_uv_present(self) -> None:
        try:
            result = self.uv.exec("--version", check=False)
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
                key = ViolationLocation(file_path=match.group("path"), line_number=int(match.group("line")))
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
                key = ViolationLocation(file_path=match.group("path"), line_number=int(match.group("line")))
                violations.setdefault(key, set()).add(match.group("code"))
        return violations

    def _apply_type_ignores(self, violations: ViolationsByLocation) -> bool:
        """Insert or merge # type: ignore[codes] on each violating line. Returns True if any file changed."""
        by_file: ViolationsByFile = {}
        for location, codes in violations.items():
            by_file.setdefault(location.file_path, {})[location.line_number] = codes

        changed = False
        for filepath, line_violations in by_file.items():
            changed |= self._apply_type_ignores_to_file(filepath=filepath, line_violations=line_violations)
        return changed

    def _apply_type_ignores_to_file(self, *, filepath: str, line_violations: LineViolations) -> bool:
        """Apply type: ignore edits to one file. Returns True if the file content changed."""
        full_path = self.repo_path / filepath
        if not full_path.exists():
            logger.warning(f"File not found, skipping: {full_path}")
            return False

        original = full_path.read_text(encoding="utf-8")
        lines = original.splitlines(keepends=True)
        # Reverse order: inserting lines for triple-quote fixes shifts later indices,
        # but those are already processed when iterating highest-to-lowest.
        for lineno, codes in sorted(line_violations.items(), reverse=True):
            idx = lineno - 1
            if idx >= len(lines):
                continue
            _apply_violation_to_line(lines=lines, idx=idx, codes=codes)

        new_content = "".join(lines)
        if new_content == original:
            return False
        logger.trace(f"Writing type: ignore comments to {filepath} in lines: {sorted(line_violations.keys())}")
        full_path.write_text(new_content, encoding="utf-8")
        return True

    def _apply_ignores(self) -> None:
        for iteration in range(1, _MAX_MYPY_ITERATIONS + 1):
            if not self._process_mypy_iteration(iteration):
                break

    def _process_mypy_iteration(self, iteration: int) -> bool:
        """Run the type checker and apply ignores for one iteration. Returns True if should continue."""
        logger.info(f"Running mypy (iteration {iteration}/{_MAX_MYPY_ITERATIONS})...")
        result = self._run_type_checker()

        if result.returncode == 0:
            logger.info("mypy passed with no errors")
            return False

        raw_output = result.stdout + result.stderr
        # Normalize joins wrapped lines from pretty=true (e.g. long messages split across
        # lines). Parsers that match non-path standalone messages (like invalid package
        # names) use raw_output to avoid losing lines that get joined away.
        output = _normalize_mypy_output(raw_output)
        violations = self._parse_violations(output)
        violations, newly_excluded_syntax = self._handle_syntax_violations(violations)
        newly_excluded_uncoded = self._exclude_blocking_uncoded_errors(output)
        newly_excluded_invalid_pkg = self._exclude_invalid_package_names(raw_output)

        if (
            not violations
            and not newly_excluded_syntax
            and not newly_excluded_uncoded
            and not newly_excluded_invalid_pkg
        ):
            logger.info("No parseable violations found; stopping")
            return False

        made_progress = newly_excluded_syntax or newly_excluded_uncoded or newly_excluded_invalid_pkg
        if violations:
            logger.info(f"Found {len(violations)} violations, applying type: ignore comments...")
            files_changed = self._apply_type_ignores(violations)
            if files_changed:
                made_progress = True
                self._run_ruff()

        if not made_progress:
            logger.info("No progress made (violations exist but files unchanged); stable state reached, stopping")
            return False
        return True

    def _handle_syntax_violations(self, violations: ViolationsByLocation) -> SyntaxHandlingResult:
        """Exclude syntax-error files. Returns (remaining_violations, newly_excluded)."""
        syntax_files = {loc.file_path for loc, codes in violations.items() if "syntax" in codes}
        if not syntax_files:
            return SyntaxHandlingResult(violations=violations, newly_excluded=False)
        logger.debug(f"Syntax violations in {len(syntax_files)} file(s): {syntax_files}")
        newly_excluded = self._exclude_mypy_files(syntax_files)
        if not newly_excluded:
            # File-level exclusion already present but mypy still reports the file.
            # mypy cannot prevent discovery-stage syntax errors via file-level patterns
            # (e.g. when the file is imported during package discovery). Escalate to
            # excluding the parent directory.
            parent_dirs = {str(Path(f).parent) + "/" for f in syntax_files}
            logger.debug(f"File-level exclusion ineffective; escalating to parent dirs: {parent_dirs}")
            newly_excluded = self._exclude_mypy_files(parent_dirs)
        remaining = {loc: codes for loc, codes in violations.items() if loc.file_path not in syntax_files}
        return SyntaxHandlingResult(violations=remaining, newly_excluded=newly_excluded)

    def _exclude_mypy_files(self, files: set[str]) -> bool:
        """Add files to [tool.mypy] exclude list in pyproject.toml (as regex patterns).

        Returns True if new files were actually added, False if all were already excluded.
        """
        logger.info(f"Excluding {len(files)} file(s) with syntax errors from mypy: {files}")
        data = self.pyproject.read()
        tool_section: Any = data["tool"]
        mypy_section: Any = tool_section["mypy"]
        existing: set[str] = set(mypy_section.get("exclude", []))
        new_excludes = existing | {re.escape(f) for f in files}
        if new_excludes == existing:
            return False
        mypy_section["exclude"] = sorted(new_excludes)
        self.pyproject.write(data)
        return True

    def _exclude_invalid_package_names(self, output: str) -> bool:
        """Exclude directories that are not valid Python package names (e.g. 'fonts-standard').

        Mypy reports these as fatal errors with no file/line context. We find matching
        directories under the repo root and add regex patterns to the mypy exclude list.

        Returns True if any directories were excluded.
        """
        names = set(_MYPY_INVALID_PKG_NAME_RE.findall(output))
        if not names:
            return False
        dirs: set[str] = set()
        for name in names:
            for found in self.tools.repo_path.rglob(name):
                if found.is_dir():
                    dirs.add(str(found.relative_to(self.tools.repo_path)) + "/")
        if not dirs:
            return False
        logger.info(f"Excluding invalid package name directories: {sorted(dirs)}")
        return self._exclude_mypy_files(dirs)

    def _exclude_blocking_uncoded_errors(self, output: str) -> bool:
        """Exclude files with no-code blocking errors. Returns True if new files were excluded.

        "Found twice" errors are always blocking and are detected unconditionally.
        Other uncoded errors are only acted on when mypy confirms they blocked checking,
        since dmypy may omit the "errors prevented further checking" summary line.
        """
        has_blocking_error = "errors prevented further checking" in output or bool(_MYPY_FOUND_TWICE_RE.search(output))
        if not has_blocking_error:
            return False
        files = self._parse_uncoded_error_files(output)
        if not files:
            logger.debug("Blocking error detected but no uncoded error files identified")
            return False
        logger.debug(f"Blocking uncoded errors in {len(files)} file(s): {files}")
        return self._exclude_mypy_files(files)

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
            logger.debug("Ruff not configured; skipping ruff suppress pass")
            return
        logger.debug("Running ruff suppress pass after mypy edits")
        RuffBoost(tools=self.tools).run_suppress_iterations()

    def _configure_mypy(self) -> None:
        self._add_mypy()
        logger.info("Configuring [tool.mypy] strict = true in pyproject.toml...")
        pyproject_data = self.pyproject.read()
        pyproject_data = self._ensure_mypy_config(pyproject_data)
        self.pyproject.write(pyproject_data)
        self._configure_extras()
        self.git.commit("🔧 Configure mypy with strict mode", no_verify=True)
        logger.info("Committed mypy configuration")

    def _add_mypy(self) -> None:
        self.uv.add_package("mypy", group="lint")
        self.uv.sync_group("lint")


class MypyBoost(BaseMypyBoost):
    """Boost that silences mypy violations using plain mypy (authoritative, slower)."""

    def commit_message(self) -> str:
        return "✅ Silence mypy violations"

    def _run_type_checker(self) -> subprocess.CompletedProcess[str]:
        return self.uv.exec("run", "--no-sync", "mypy", ".", check=False)


class DmypyBoost(BaseMypyBoost):
    """Boost that silences mypy violations using the dmypy daemon (faster, minor divergence risk).

    Not enabled by default. Use --only dmypy to opt in.
    dmypy finds some real errors that plain mypy misses (e.g. in complex inheritance), but also
    produces false positives that result in unnecessary type: ignore comments.
    """

    def commit_message(self) -> str:
        return "✅ Silence dmypy violations"

    def _run_type_checker(self) -> subprocess.CompletedProcess[str]:
        self.uv.exec("run", "--no-sync", "dmypy", "kill", check=False)
        shutil.rmtree(self.repo_path / ".mypy_cache", ignore_errors=True)
        (self.repo_path / ".dmypy.json").unlink(missing_ok=True)
        return self.uv.exec("run", "--no-sync", "dmypy", "run", ".", check=False)

    def _configure_extras(self) -> None:
        self._add_dmypy_to_gitignore()

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


def _find_unclosed_triple_quote_pos(line: str) -> TripleQuotePos | None:
    """Return (position, triple_quote) of the first unclosed triple-quote opener in line.

    Scans left-to-right, pairing openers with closers. Single- and double-quoted
    non-triple strings are skipped so that e.g. '\"\"\"' is not mistaken for a
    triple-quote opener. If the last opener has no closer on the same line, returns
    its position so we can place the comment before it.
    """
    stripped = line.rstrip("\n").rstrip("\r")
    i = 0
    while i < len(stripped):
        ch = stripped[i]
        if ch not in ('"', "'"):
            i += 1
            continue
        triple_quote = ch * 3
        if stripped[i : i + 3] == triple_quote:
            closer = stripped.find(triple_quote, i + 3)
            if closer == -1:
                return TripleQuotePos(position=i, quote=triple_quote)
            i = closer + 3
        else:
            # Single-char quoted string: skip to its end, respecting backslash escapes,
            # so that e.g. '\"\"\"' is not mistaken for a triple-quote opener.
            i += 1  # skip opening quote
            while i < len(stripped):
                if stripped[i] == "\\":
                    i += 2  # skip escaped character
                elif stripped[i] == ch:
                    i += 1  # skip closing quote
                    break
                else:
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

    For function calls (code_part ends with '('), the comment is placed after '(' and
    the triple-quote is moved to the next line. The caller must process violations in
    reverse line order so that inserted lines do not shift pending indices.

    For assignments, the comment is placed on the CLOSING triple-quote line instead of
    the opening line. mypy attributes the error to the opening line but recognises a
    type: ignore on the closing line as suppressing it — and this avoids creating
    parenthesised wrappers that ruff may remove via UP034 (causing oscillation).
    """
    raw_line = lines[idx]
    result = _find_unclosed_triple_quote_pos(raw_line)
    if result is None:
        lines[idx] = _merge_type_ignore(raw_line=raw_line, codes=codes)
        return

    line = raw_line.rstrip("\n").rstrip("\r")
    eol = raw_line[len(line) :]
    code_part = line[: result.position]

    if code_part.rstrip().endswith("("):
        # Function call: place comment after ( and move triple-quote to next line.
        type_ignore = f"# type: ignore[{', '.join(sorted(codes))}]"
        lines[idx] = f"{code_part.rstrip()}  {type_ignore}{eol}"
        base_indent = len(line) - len(line.lstrip())
        triple_quote_content = line[result.position :].lstrip()
        new_indent = " " * (base_indent + 4)
        new_line = f"{new_indent}{triple_quote_content}{eol}"
        lines.insert(idx + 1, new_line)
        return

    _place_type_ignore_on_closing_triple_quote(
        lines=lines,
        idx=idx,
        triple_quote=result.quote,
        codes=codes,
    )


def _place_type_ignore_on_closing_triple_quote(
    *,
    lines: list[str],
    idx: int,
    triple_quote: str,
    codes: ErrorCodes,
) -> None:
    """Handle assignment triple-quote: place type: ignore on the closing triple-quote line.

    mypy attributes assignment errors to the opening \"\"\" line but recognises a
    type: ignore on the closing \"\"\" line as suppressing it. This avoids creating ()
    wrappers that ruff may remove via UP034, which would cause an oscillation loop.
    """
    closing_idx = _find_closing_triple_quote(lines=lines, start_idx=idx + 1, quote=triple_quote)
    if closing_idx is None:
        return
    lines[closing_idx] = _merge_type_ignore(raw_line=lines[closing_idx], codes=codes)


def _apply_violation_to_line(*, lines: list[str], idx: int, codes: ErrorCodes) -> None:
    """Apply or remove type: ignore codes on a single source line."""
    codes_to_remove = {c[1:] for c in codes if c.startswith("!")}
    effective_codes = {c for c in codes if not c.startswith("!") and c != "unused-ignore"}
    # Error wins: if both tools report "error [X]" and "unused-ignore [X]", keep the ignore.
    codes_to_remove -= effective_codes
    if codes_to_remove:
        lines[idx] = _remove_type_ignore_codes(raw_line=lines[idx], codes=codes_to_remove)
    if effective_codes:
        _place_type_ignore(lines=lines, idx=idx, codes=effective_codes)
    if not codes_to_remove and not effective_codes:
        # Bare unused-ignore with no parseable codes: remove the whole comment.
        lines[idx] = _remove_type_ignore(lines[idx])


def _remove_type_ignore(raw_line: str) -> str:
    """Remove type: ignore from a line (for unused-ignore violations)."""
    line = raw_line.rstrip("\n").rstrip("\r")
    eol = raw_line[len(line) :]
    removed = _TYPE_IGNORE_RE.sub("", line).rstrip()
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
