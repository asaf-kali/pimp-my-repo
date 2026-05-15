"""Mypy boost implementation."""

import abc
import re
import shutil
from abc import abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

from loguru import logger
from tomlkit import TOMLDocument, array, table

from pimp_my_repo.core.boosts.base import Boost, BoostSkipped
from pimp_my_repo.core.boosts.ruff import RuffBoost
from pimp_my_repo.core.tools.pyproject import PyProjectNotFoundError

if TYPE_CHECKING:
    from pimp_my_repo.core.tools.subprocess import CommandResult

_MAX_MYPY_ITERATIONS = 10
_MYPY_PACKAGE = "mypy>=1.0,<1.20"  # lower-bound: 1.0 dropped typed_ast; upper-bound: bump after validating new minor

# Supports "path:line: error:", "path:line:col: error:" (--show-column-numbers), and
# "path:line:col:endline:endcol: error:" (--show-error-end).  (?::\d+)* matches zero or
# more additional colon-separated numeric segments so all three formats are captured with
# the correct path and line number.
# Greedy .* before \[code\] ensures we match the LAST [code] in the line.
_MYPY_ERROR_RE = re.compile(
    r"^(?P<path>.+?):(?P<line>\d+)(?::\d+)*: error: .*\[(?P<code>[^\]]+)\]",
)
# Detects lines that start a mypy diagnostic with a line number (path:line: ...).
_MYPY_LINE_START_RE = re.compile(r"^\S[^:]*:\d+(?::\d+)*: ")
# "note: Error code "X" not covered by "type: ignore" comment"
_MYPY_NOTE_UNCOVERED_RE = re.compile(
    r"^(?P<path>.+?):(?P<line>\d+)(?::\d+)*: note: Error code \"(?P<code>[^\"]+)\" not covered",
)
_TYPE_IGNORE_RE = re.compile(r"# type: ignore(?:\[([^\]]*)\])?")
# Matches a # type: <annotation> comment (not a # type: ignore directive).
# When present, # type: ignore must be placed AFTER it so mypy reads the annotation first.
_TYPE_ANNOTATION_COMMENT_RE = re.compile(r"^# type: (?!ignore\b)")
# Parses which codes are unused from: Unused "type: ignore[X, Y]" comment  [unused-ignore]
_MYPY_UNUSED_IGNORE_RE = re.compile(r'Unused "type: ignore\[(?P<codes>[^\]]+)\]" comment\s+\[unused-ignore\]')
# Matches any "error:" line regardless of whether it has a [code] suffix.
# (?:(?::\d+)+)? matches one or more colon-number segments (col, or col:endline:endcol).
_MYPY_ANY_ERROR_RE = re.compile(r"^(?P<path>.+?)(?:(?::\d+)+)?: error: ")
# "Source file found twice" errors must exclude the parent directory, not just the file,
# because mypy's exclude option doesn't prevent discovery-stage errors on specific files.
_MYPY_FOUND_TWICE_RE = re.compile(r"Source file found twice under different module names")
# Directories with hyphens (e.g. "fonts-standard") are invalid Python package names.
# Mypy outputs these as fatal errors with no file/line context.
_MYPY_INVALID_PKG_NAME_RE = re.compile(r"^(.+) is not a valid Python package name$", re.MULTILINE)
# Detects "Error importing plugin "X.Y.Z": No module named 'X'" errors — plugin not installed.
# These appear on pyproject.toml (not a Python file) so they can't be suppressed with # type: ignore.
_MYPY_PLUGIN_IMPORT_ERROR_RE = re.compile(r'^.+?:\d+(?::\d+)*: error: Error importing plugin "([^"]+)"')
# Detects "Error constructing plugin instance of X" — plugin is installed but crashes in __init__
# (e.g. django-stubs when SECRET_KEY env var is missing).  The class name in the error message is
# not the module path we need, so we extract the module from the __init__ frame in the traceback.
_MYPY_PLUGIN_CRASH_RE = re.compile(r"^Error constructing plugin instance of \w+", re.MULTILINE)
_MYPY_PLUGIN_CRASH_INIT_FRAME_RE = re.compile(r'File ".*?site-packages/([^"]+\.py)",.*? in __init__')


def _extract_crashed_plugin_modules(output: str) -> set[str]:
    """Return plugin module paths (e.g. 'mypy_django_plugin.main') that crashed in __init__.

    When a plugin's constructor raises (e.g. django-stubs needing SECRET_KEY), mypy prints
    "Error constructing plugin instance of X" followed by a Python traceback.  We locate the
    __init__ frame that belongs to a site-packages plugin and convert the file path to a dotted
    module name that matches what is written in [tool.mypy] plugins.
    """
    if not _MYPY_PLUGIN_CRASH_RE.search(output):
        return set()
    result: set[str] = set()
    for m in _MYPY_PLUGIN_CRASH_INIT_FRAME_RE.finditer(output):
        # 'mypy_django_plugin/main.py' → 'mypy_django_plugin.main'
        module = m.group(1).replace("/", ".").removesuffix(".py")
        result.add(module)
    return result


def _apply_note_line(line: str, violations: ViolationsByLocation) -> None:
    """Handle a note: diagnostic line, adding to violations if it carries an error code."""
    match = _MYPY_NOTE_UNCOVERED_RE.match(line)
    if not match:
        return
    key = ViolationLocation(file_path=match.group("path"), line_number=int(match.group("line")))
    violations.setdefault(key, set()).add(match.group("code"))


def _apply_coded_error_line(
    line: str,
    match: re.Match[str],
    violations: ViolationsByLocation,
    syntax_files: set[str],
) -> None:
    """Handle a coded error line (has [code] bracket), updating violations and/or syntax_files."""
    code = match.group("code")
    if code == "syntax":
        syntax_files.add(match.group("path"))
    key = ViolationLocation(file_path=match.group("path"), line_number=int(match.group("line")))
    if code != "unused-ignore":
        violations.setdefault(key, set()).add(code)
        return
    # Extract which specific codes are unused so we only remove those,
    # leaving any codes that are still suppressing real errors intact.
    unused_match = _MYPY_UNUSED_IGNORE_RE.search(line)
    if not unused_match:
        violations.setdefault(key, set()).add("unused-ignore")
        return
    for uc in unused_match.group("codes").split(","):
        violations.setdefault(key, set()).add(f"!{uc.strip()}")


def _apply_diagnostic_line(  # noqa: PLR0913
    line: str,
    violations: ViolationsByLocation,
    syntax_files: set[str],
    uncoded_error_files: set[str],
    missing_plugins: set[str],
    unhandled_lines: list[str],
) -> None:
    """Classify one normalized diagnostic line (already confirmed to have path:line: prefix)."""
    if ": note: " in line:
        _apply_note_line(line, violations)
        return
    plugin_match = _MYPY_PLUGIN_IMPORT_ERROR_RE.match(line)
    if plugin_match:
        missing_plugins.add(plugin_match.group(1))
        return
    match = _MYPY_ERROR_RE.match(line)
    if match:
        _apply_coded_error_line(line, match, violations, syntax_files)
        return
    m = _MYPY_ANY_ERROR_RE.match(line)
    if m:
        uncoded_error_files.add(m.group("path"))
        return
    unhandled_lines.append(line)


def _parse_mypy_output(*, raw_output: str) -> ParsedMypyOutput:
    """Parse mypy output in a single pass, classifying each line.

    Requires ``pretty = false`` (PMR sets this) so each diagnostic is one line.

    Each line falls into exactly one category:
    - Diagnostic with line number (path:line: ...) → coded error, note, uncoded error, or unhandled
    - Error without line number (path: error: ...)  → found_twice_dirs or uncoded_error_files
    - Invalid package name message                  → invalid_pkg_names
    - Known summary/info line                       → skipped
    - Anything else                                 → unhandled_lines (triggers RuntimeError upstream)
    """
    violations: ViolationsByLocation = {}
    syntax_files: set[str] = set()
    uncoded_error_files: set[str] = set()
    found_twice_dirs: set[str] = set()
    invalid_pkg_names: set[str] = set()
    missing_plugins: set[str] = _extract_crashed_plugin_modules(raw_output)
    unhandled_lines: list[str] = []
    has_blocking_error = False

    for raw_line in raw_output.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if "errors prevented further checking" in line:
            has_blocking_error = True

        # Category 1: Diagnostic line with line number (path:line: ...)
        if _MYPY_LINE_START_RE.match(line):
            _apply_diagnostic_line(
                line, violations, syntax_files, uncoded_error_files, missing_plugins, unhandled_lines
            )
            continue

        # Category 2: Error line without line number (path: error: ...)
        m = _MYPY_ANY_ERROR_RE.match(line)
        if m:
            filepath = m.group("path")
            if _MYPY_FOUND_TWICE_RE.search(line):
                found_twice_dirs.add(str(Path(filepath).parent) + "/")
                has_blocking_error = True
            else:
                uncoded_error_files.add(filepath)
            continue

        # Category 3: Invalid package name
        m = _MYPY_INVALID_PKG_NAME_RE.match(line)
        if m:
            invalid_pkg_names.add(m.group(1))
            continue

        # Category 4: Known summary/info lines — skip silently
        if line.startswith(("Found ", "Success: ", "note: ")):
            continue

        unhandled_lines.append(line)

    logger.trace(
        f"Parsed mypy output: {len(violations)} violations, "
        f"{len(syntax_files)} syntax files, {len(uncoded_error_files)} uncoded error files, "
        f"{len(found_twice_dirs)} found-twice dirs, {len(invalid_pkg_names)} invalid pkg names, "
        f"{len(missing_plugins)} missing plugins, "
        f"blocking={has_blocking_error}, {len(unhandled_lines)} unhandled lines"
    )
    if unhandled_lines:
        logger.debug(f"Unhandled mypy lines: {unhandled_lines}")

    return ParsedMypyOutput(
        violations=violations,
        syntax_files=syntax_files,
        uncoded_error_files=uncoded_error_files,
        found_twice_dirs=found_twice_dirs,
        invalid_pkg_names=invalid_pkg_names,
        missing_plugins=missing_plugins,
        has_blocking_error=has_blocking_error,
        unhandled_lines=unhandled_lines,
    )


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


class ParsedMypyOutput(NamedTuple):
    violations: ViolationsByLocation  # coded errors (syntax-file violations already stripped)
    syntax_files: set[str]  # files with [syntax] errors — will be excluded entirely
    uncoded_error_files: set[str]  # error lines without [code], only excluded if blocking
    found_twice_dirs: set[str]  # parent dirs for "source file found twice" errors
    invalid_pkg_names: set[str]  # names from "X is not a valid Python package name"
    missing_plugins: set[str]  # plugin names from "Error importing plugin X" — not installed
    has_blocking_error: bool  # "errors prevented further checking" in output
    unhandled_lines: list[str]  # diagnostic lines not matched by any known pattern


class BaseMypyBoost(Boost, abc.ABC):
    """Abstract base for mypy-based boosts. Subclasses supply the type-checker runner."""

    def apply(self) -> None:
        """Add mypy, configure strict mode, commit, then suppress all violations."""
        self._verify_preconditions()
        if not self.skip_config:
            self._configure_mypy()
        self._apply_ignores()

    @abstractmethod
    def _run_type_checker(self) -> CommandResult:
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
                raise BoostSkipped(msg)
        except (FileNotFoundError, OSError) as exc:
            msg = "uv is not installed"
            raise BoostSkipped(msg) from exc

    def _verify_pyproject_present(self) -> None:
        try:
            self.pyproject.verify_present()
        except PyProjectNotFoundError as exc:
            msg = "No pyproject.toml found"
            raise BoostSkipped(msg) from exc

    def _ensure_mypy_config(self, data: TOMLDocument) -> TOMLDocument:
        if "tool" not in data:
            data["tool"] = table()
        tool_section: Any = data["tool"]
        if "mypy" not in tool_section:
            tool_section["mypy"] = table()
        mypy_section: Any = tool_section["mypy"]
        mypy_section["strict"] = True
        return data

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
        logger.trace(f"Writing 'type: ignore' comments to {filepath} in lines: {sorted(line_violations.keys())}")
        full_path.write_text(new_content, encoding="utf-8")
        return True

    def _apply_ignores(self) -> None:
        for iteration in range(1, _MAX_MYPY_ITERATIONS + 1):
            if not self._process_mypy_iteration(iteration):
                self._enable_mypy_pretty()
                break

    def _enable_mypy_pretty(self) -> None:
        """Set pretty = true in [tool.mypy] so end-users get readable mypy output."""
        pyproject_data = self.pyproject.read()
        tool_section: Any = pyproject_data.get("tool")
        if tool_section is None or "mypy" not in tool_section:
            return
        tool_section["mypy"]["pretty"] = True
        self.pyproject.write(pyproject_data)

    def _process_mypy_iteration(self, iteration: int) -> bool:
        """Run the type checker and apply ignores for one iteration. Returns True if should continue."""
        logger.info(f"Running mypy (iteration {iteration}/{_MAX_MYPY_ITERATIONS})...")
        result = self._run_type_checker()

        if result.returncode == 0:
            logger.info("mypy passed with no errors")
            return False

        raw_output = result.stdout + result.stderr
        logger.trace(f"Raw mypy output:\n{raw_output}")
        parsed = _parse_mypy_output(raw_output=raw_output)

        newly_removed_plugins = self._remove_missing_plugins(parsed.missing_plugins)
        newly_excluded_syntax = self._apply_syntax_exclusions(parsed.syntax_files)
        newly_excluded_uncoded = self._apply_uncoded_exclusions(
            uncoded_error_files=parsed.uncoded_error_files,
            found_twice_dirs=parsed.found_twice_dirs,
            has_blocking_error=parsed.has_blocking_error,
        )
        newly_excluded_invalid_pkg = self._apply_invalid_pkg_handling(parsed.invalid_pkg_names)
        violations = parsed.violations

        if (
            not violations
            and not newly_removed_plugins
            and not newly_excluded_syntax
            and not newly_excluded_uncoded
            and not newly_excluded_invalid_pkg
        ):
            if parsed.unhandled_lines:
                lines_str = "\n".join(f"  {line}" for line in parsed.unhandled_lines)
                msg = f"mypy returned errors that could not be handled:\n{lines_str}"
                raise RuntimeError(msg)
            logger.warning("No further progress possible; stable state reached, stopping")
            return False

        made_progress = (
            newly_removed_plugins or newly_excluded_syntax or newly_excluded_uncoded or newly_excluded_invalid_pkg
        )
        if violations:
            logger.info(f"Found {len(violations)} violations, applying type: ignore comments...")
            files_changed = self._apply_type_ignores(violations)
            if files_changed:
                made_progress = True
                if self._run_ruff():
                    made_progress = True

        if not made_progress:
            logger.warning("No progress made (violations exist but files unchanged); stable state reached, stopping")
            return False
        return True

    def _apply_syntax_exclusions(self, syntax_files: set[str]) -> bool:
        """Exclude syntax-error files from mypy. Returns True if any new exclusion was added."""
        if not syntax_files:
            return False
        logger.debug(f"Syntax violations in {len(syntax_files)} file(s): {syntax_files}")
        return self._exclude_mypy_files(syntax_files)

    def _exclude_mypy_files(self, files: set[str]) -> bool:
        """Add files to [tool.mypy] exclude list in pyproject.toml (as regex patterns).

        Returns True if new files were actually added, False if all were already excluded.
        """
        data = self.pyproject.read()
        tool_section: Any = data["tool"]
        mypy_section: Any = tool_section["mypy"]
        existing: set[str] = set(mypy_section.get("exclude", []))
        new_excludes = existing | {re.escape(f) for f in files}
        if new_excludes == existing:
            logger.debug(f"All {len(files)} path(s) already excluded from mypy: {files}")
            return False
        newly_added = new_excludes - existing
        logger.info(f"Excluding {len(newly_added)} new path(s) from mypy: {newly_added}")
        exclude_array = array()
        exclude_array.multiline(True)  # noqa: FBT003
        for item in sorted(new_excludes):
            exclude_array.append(item)
        mypy_section["exclude"] = exclude_array
        self.pyproject.write(data)
        return True

    def _apply_invalid_pkg_handling(self, names: set[str]) -> bool:
        """Exclude or rename directories that are not valid Python package names.

        Names with spaces are renamed (spaces → underscores). Other names (e.g. hyphens)
        are located on disk and added to the mypy exclude list.

        Returns True if any progress was made (exclusion or rename).
        """
        if not names:
            return False
        space_names = {n for n in names if " " in n}
        other_names = names - space_names
        made_progress = False
        if space_names:
            made_progress |= self._rename_space_dirs(space_names)
        if other_names:
            dirs = self._find_invalid_pkg_dirs(other_names)
            if dirs:
                logger.info(f"Excluding invalid package name directories: {sorted(dirs)}")
                made_progress |= self._exclude_mypy_files(dirs)
        return made_progress

    def _find_invalid_pkg_dirs(self, names: set[str]) -> set[str]:
        """Search for directories matching any of the given names under the repo root."""
        dirs: set[str] = set()
        for name in names:
            for found in self.tools.repo_path.rglob(name):
                if found.is_dir():
                    dirs.add(str(found.relative_to(self.tools.repo_path)) + "/")
        return dirs

    def _rename_space_dirs(self, names: set[str]) -> bool:
        """Rename directories whose names contain spaces, replacing spaces with underscores.

        Returns True if any directory was renamed.
        """
        renamed = False
        for name in names:
            for found in self.tools.repo_path.rglob(name):
                if not found.is_dir():
                    continue
                new_name = name.replace(" ", "_")
                found.rename(found.parent / new_name)
                logger.info(f"Renamed invalid package directory: '{found.name}' -> '{new_name}'")
                renamed = True
        return renamed

    def _remove_missing_plugins(self, plugin_names: set[str]) -> bool:
        """Remove plugins from [tool.mypy] plugins that failed to import (not installed).

        Plugins listed in pyproject.toml but missing from the lint environment can't be
        suppressed with # type: ignore (the error appears on pyproject.toml, not a .py file).
        Removing them lets mypy run in strict mode without the plugin-specific checks.

        Returns True if any plugin was removed.
        """
        if not plugin_names:
            return False
        data = self.pyproject.read()
        tool_section: Any = data.get("tool")
        if not isinstance(tool_section, dict):
            return False
        mypy_section: Any = tool_section.get("mypy")
        if not isinstance(mypy_section, dict):
            return False
        existing_plugins: list[str] = list(mypy_section.get("plugins", []))
        new_plugins = [p for p in existing_plugins if p not in plugin_names]
        if len(new_plugins) == len(existing_plugins):
            return False
        removed = set(existing_plugins) - set(new_plugins)
        logger.info(f"Removing uninstallable mypy plugins: {sorted(removed)}")
        if new_plugins:
            plugins_array = array()
            plugins_array.multiline(True)  # noqa: FBT003
            for p in new_plugins:
                plugins_array.append(p)
            mypy_section["plugins"] = plugins_array
        else:
            del mypy_section["plugins"]
        self.pyproject.write(data)
        return True

    def _apply_uncoded_exclusions(
        self,
        *,
        uncoded_error_files: set[str],
        found_twice_dirs: set[str],
        has_blocking_error: bool,
    ) -> bool:
        """Exclude files/dirs with uncoded errors that cannot be suppressed inline.

        "Found twice" dirs are always excluded. Other uncoded-error files are only
        excluded when mypy confirms they blocked further checking, since dmypy may omit
        the "errors prevented further checking" summary line.

        Returns True if any new exclusion was added.
        """
        if not has_blocking_error:
            return False
        files = found_twice_dirs | uncoded_error_files
        if not files:
            logger.debug("Blocking error detected but no uncoded error files identified")
            return False
        logger.debug(f"Blocking uncoded errors in {len(files)} file(s): {files}")
        return self._exclude_mypy_files(files)

    def _run_ruff(self) -> bool:
        """Run ruff suppress iterations if ruff is configured. Returns True if ruff found violations."""
        data = self.pyproject.read()
        tool_section = data.get("tool")
        if not tool_section or "ruff" not in tool_section:
            logger.debug("Ruff not configured; skipping ruff suppress pass")
            return False
        logger.debug("Running ruff suppress pass after mypy edits")
        return RuffBoost(tools=self.tools, run_config=self.run_config).run_suppress_iterations()

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
        if not self.pyproject.is_package_in_deps("mypy"):
            self.uv.add_package(_MYPY_PACKAGE, group="lint")
            self.uv.sync_group("lint")

    def _clear_mypy_cache(self) -> None:
        """Clear mypy cache to ensure changes take effect immediately."""
        shutil.rmtree(self.repo_path / ".mypy_cache", ignore_errors=True)
        (self.repo_path / ".dmypy.json").unlink(missing_ok=True)


class MypyBoost(BaseMypyBoost):
    """Boost that silences mypy violations using plain mypy (authoritative, slower)."""

    def commit_message(self) -> str:
        return "✅ Silence mypy violations"

    def _run_type_checker(self) -> CommandResult:
        self._clear_mypy_cache()
        result = self.uv.exec("run", "--no-sync", "mypy", ".", "--no-pretty", check=False, log_on_error=False)
        self._clear_mypy_cache()
        return result


class DmypyBoost(BaseMypyBoost):
    """Boost that silences mypy violations using the dmypy daemon (faster, minor divergence risk).

    Not enabled by default. Use --only dmypy to opt in.
    dmypy finds some real errors that plain mypy misses (e.g. in complex inheritance), but also
    produces false positives that result in unnecessary type: ignore comments.
    """

    def commit_message(self) -> str:
        return "✅ Silence dmypy violations"

    def _run_type_checker(self) -> CommandResult:
        self._clear_mypy_cache()
        self.uv.exec("run", "--no-sync", "dmypy", "kill", check=False, log_on_error=False)
        result = self.uv.exec(
            "run", "--no-sync", "dmypy", "run", "--", ".", "--no-pretty", check=False, log_on_error=False
        )
        self._clear_mypy_cache()
        return result

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

    Normally type: ignore is placed FIRST (before noqa and other trailing comments),
    merging all existing type: ignore comments into one.

    Exception: when a ``# type: <annotation>`` comment is present (a legacy PEP 484
    type comment), mypy only reads the FIRST ``# type:`` directive on the line.
    Placing ``# type: ignore`` before the annotation would hide the annotation.
    In this case ``# type: ignore`` is appended AFTER the annotation so that mypy
    reads the annotation first and then suppresses the error.
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

    # Legacy PEP 484 type annotation comment: mypy reads only the first "# type:" directive
    # on a line, so the ignore directive must be appended after the annotation, not before.
    if remaining and _TYPE_ANNOTATION_COMMENT_RE.match(remaining):
        return f"{code}  {remaining}  {new_type_ignore}{eol}"

    # Default: type: ignore FIRST, then remaining comments (noqa etc.) after.
    if remaining and remaining != "#":
        return f"{code}  {new_type_ignore}  {remaining}{eol}"
    return f"{code}  {new_type_ignore}{eol}"
