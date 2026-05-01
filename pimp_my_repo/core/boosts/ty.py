"""Ty boost implementation."""

import re
from typing import TYPE_CHECKING, Any, NamedTuple

from loguru import logger
from tomlkit import TOMLDocument, array, table

from pimp_my_repo.core.boosts.base import Boost, BoostSkipped
from pimp_my_repo.core.boosts.ruff import RuffBoost
from pimp_my_repo.core.tools.pyproject import PyProjectNotFoundError

if TYPE_CHECKING:
    from pimp_my_repo.core.tools.subprocess import CommandResult

_MAX_TY_ITERATIONS = 10
_TY_PACKAGE = "ty>=0.0.1,<0.1"  # upper-bound: bump after validating new minor

# Parses concise output: "path:line:col: error[rule-name] message"
# (?::\d+)* handles optional col / end-line / end-col segments
_TY_VIOLATION_RE = re.compile(
    r"^(?P<path>.+?):(?P<line>\d+)(?::\d+)*: (?:error|warning)\[(?P<code>[^\]]+)\]",
    re.MULTILINE,
)

# Parses io errors: "path: error[io] message" (no line number)
_TY_IO_ERROR_RE = re.compile(r"^(?P<path>[^\n:]+): error\[io\]", re.MULTILINE)

_TY_IGNORE_RE = re.compile(r"#\s*ty:\s*ignore(?:\[([^\]]*)\])?")

_UNUSED_IGNORE_CODE = "unused-ignore-comment"
_INVALID_SYNTAX_CODE = "invalid-syntax"


class ViolationLocation(NamedTuple):
    """A single violation location: file path and line number."""

    filepath: str
    lineno: int


class TripleQuotePos(NamedTuple):
    """Position and quote character of an unclosed triple-quote opener."""

    position: int
    quote: str


type ErrorCodes = set[str]
type ViolationsByLocation = dict[ViolationLocation, ErrorCodes]
type LineViolations = dict[int, ErrorCodes]
type ViolationsByFile = dict[str, LineViolations]


class TyBoost(Boost):
    """Boost for integrating the ty type checker."""

    def apply(self) -> None:
        """Add ty, configure it, then suppress all violations."""
        self._verify_uv_present()
        self._verify_pyproject_present()

        if not self.pyproject.is_package_in_deps("ty"):
            self.uv.add_package(_TY_PACKAGE, group="lint")
            self.uv.sync_group("lint")

        logger.info("Configuring [tool.ty] in pyproject.toml...")
        pyproject_data = self.pyproject.read()
        pyproject_data = self._ensure_ty_config(pyproject_data)
        self.pyproject.write(pyproject_data)

        self.git.commit("🔧 Configure ty", no_verify=True)

        self._run_suppress_iterations()

    def commit_message(self) -> str:
        """Generate commit message for ty boost."""
        return "✅ Silence ty violations"

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

    def _ensure_ty_config(self, data: TOMLDocument) -> TOMLDocument:
        if "tool" not in data:
            data["tool"] = table()
        tool_section: Any = data["tool"]
        if "ty" not in tool_section:
            tool_section["ty"] = table()
        ty_section: Any = tool_section["ty"]
        # Treat warnings as errors — equivalent of mypy's strict mode for ty.
        # Warnings (e.g. ambiguous-protocol-member) otherwise exit 0 and go unnoticed.
        if "terminal" not in ty_section:
            ty_section["terminal"] = table()
        ty_section["terminal"]["error-on-warning"] = True
        # Suppress spurious "unused ignore" warnings that cause oscillation loops:
        # - unused-ignore-comment: ty flags its own suppress comments as unused when
        #   its type inference is inconsistent across runs.
        # - unused-type-ignore-comment: mypy's # type: ignore comments from the repo
        #   are correct for mypy but ty considers them unused — we should not remove them.
        if "rules" not in ty_section:
            ty_section["rules"] = table()
        rules_section: Any = ty_section["rules"]
        rules_section["unused-ignore-comment"] = "ignore"
        rules_section["unused-type-ignore-comment"] = "ignore"
        return data

    def _run_ty_check(self) -> CommandResult:
        logger.debug("Running ty check...")
        return self.uv.exec(
            "run",
            "--no-sync",
            "ty",
            "check",
            ".",
            "--output-format",
            "concise",
            check=False,
            log_on_error=False,
        )

    def _parse_ty_output(self, stdout: str) -> ViolationsByLocation:
        """Parse ty concise output into {ViolationLocation: {rule_codes}}."""
        violations: ViolationsByLocation = {}
        for m in _TY_VIOLATION_RE.finditer(stdout):
            key = ViolationLocation(filepath=m.group("path"), lineno=int(m.group("line")))
            violations.setdefault(key, set()).add(m.group("code"))
        return violations

    def _parse_io_errors(self, stdout: str) -> set[str]:
        """Return file paths that produced error[io] (unreadable files)."""
        return {m.group("path") for m in _TY_IO_ERROR_RE.finditer(stdout)}

    def _add_ty_excludes(self, paths: set[str]) -> None:
        """Add paths to [tool.ty.src] exclude in pyproject.toml."""
        data = self.pyproject.read()
        data = self._ensure_ty_config(data)
        ty_section: Any = data["tool"]["ty"]  # type: ignore[index]
        if "src" not in ty_section:
            ty_section["src"] = table()
        src_section: Any = ty_section["src"]
        existing: list[str] = list(src_section.get("exclude", []))
        new_paths = sorted(_escape_ty_glob(p) for p in paths if _escape_ty_glob(p) not in existing)
        if not new_paths:
            return
        logger.info(f"Excluding {len(new_paths)} file(s) from ty: {new_paths}")
        updated = array()
        updated.extend(existing + new_paths)
        src_section["exclude"] = updated
        self.pyproject.write(data)

    def _apply_ty_ignores(self, violations: ViolationsByLocation) -> bool:
        """Insert, merge, or remove # ty: ignore[codes] on each violating line.

        Returns True if at least one file was actually modified.
        """
        by_file: ViolationsByFile = {}
        for location, codes in violations.items():
            by_file.setdefault(location.filepath, {})[location.lineno] = codes

        modified = False
        for filepath, line_violations in by_file.items():
            if self._apply_ty_ignores_to_file(filepath=filepath, line_violations=line_violations):
                modified = True
        return modified

    def _apply_ty_ignores_to_file(self, *, filepath: str, line_violations: LineViolations) -> bool:
        """Apply ty: ignore comments to a single file. Returns True if the file was modified."""
        full_path = self.repo_path / filepath
        if not full_path.exists():
            logger.warning(f"File not found, skipping: {full_path}")
            return False

        original = full_path.read_text(encoding="utf-8")
        lines = original.splitlines(keepends=True)
        # Reverse order so that line insertions (triple-quote handling) don't shift pending indices.
        for lineno, codes in sorted(line_violations.items(), reverse=True):
            idx = lineno - 1
            if idx < 0:
                continue
            if idx >= len(lines):
                lines.insert(0, f"# ty: ignore[{', '.join(sorted(codes))}]\n")
            else:
                _place_ty_ignore(lines=lines, idx=idx, codes=codes)

        new_content = "".join(lines)
        if new_content == original:
            return False
        logger.trace(f"Writing 'ty: ignore' comments to {filepath} in lines: {sorted(line_violations.keys())}")
        full_path.write_text(new_content, encoding="utf-8")
        return True

    def _suppress_violations_iteration(self) -> bool:
        """Run one ty-check + ruff-suppress cycle. Returns True if another iteration is needed."""
        result = self._run_ty_check()

        if result.returncode == 0:
            logger.info("ty check passed with no violations")
            return False

        stdout = result.stdout or ""
        acted = False

        io_paths = self._parse_io_errors(stdout)
        if io_paths:
            self._add_ty_excludes(io_paths)
            acted = True

        violations = self._parse_ty_output(stdout)

        # Files with invalid-syntax cannot have inline suppression; exclude them instead.
        syntax_error_files = {loc.filepath for loc, codes in violations.items() if _INVALID_SYNTAX_CODE in codes}
        if syntax_error_files:
            self._add_ty_excludes(syntax_error_files)
            violations = {loc: codes for loc, codes in violations.items() if loc.filepath not in syntax_error_files}
            acted = True

        if violations:
            logger.info(f"Found {len(violations)} violations, applying ty: ignore comments...")
            changed = self._apply_ty_ignores(violations)
            if changed:
                acted = True
            elif not acted:
                # No progress: violations are in positions that can't be suppressed inline
                # (e.g. inside triple-quoted strings). Exclude the affected files.
                stuck_files = {loc.filepath for loc in violations}
                logger.warning(f"Could not suppress {len(violations)} violation(s); excluding: {stuck_files}")
                self._add_ty_excludes(stuck_files)
                acted = True

        if not acted:
            logger.info("No parseable violations found; stopping")
            return False

        if self._run_ruff():
            acted = True

        return acted

    def _run_ruff(self) -> bool:
        """Run ruff suppress iterations if ruff is configured. Returns True if ruff found violations."""
        data = self.pyproject.read()
        tool_section = data.get("tool")
        if not tool_section or "ruff" not in tool_section:
            return False
        logger.debug("Running ruff suppress pass after ty edits")
        return RuffBoost(tools=self.tools).run_suppress_iterations()

    def _run_suppress_iterations(self) -> None:
        """Run ty+ruff check+suppress iterations until stable."""
        for iteration in range(1, _MAX_TY_ITERATIONS + 1):
            logger.info(f"Running ty (iteration {iteration}/{_MAX_TY_ITERATIONS})...")
            if not self._suppress_violations_iteration():
                break


def _escape_ty_glob(path: str) -> str:
    """Escape characters that are invalid in ty's glob patterns (e.g. spaces)."""
    return path.replace(" ", "\\ ")


def _find_unclosed_triple_quote_pos(line: str) -> TripleQuotePos | None:
    """Return (position, quote) of the first unclosed triple-quote opener in line.

    Scans left-to-right, pairing openers with closers. Single-quoted non-triple strings
    are skipped so that e.g. '\"\"\"' is not mistaken for a triple-quote opener.
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
            # Single-char quoted string: skip to its end, respecting backslash escapes.
            i += 1
            while i < len(stripped):
                if stripped[i] == "\\":
                    i += 2
                elif stripped[i] == ch:
                    i += 1
                    break
                else:
                    i += 1
    return None


def _place_ty_ignore(*, lines: list[str], idx: int, codes: ErrorCodes) -> None:
    """Apply ty: ignore to lines[idx], handling triple-quoted string openings.

    If the line opens an unclosed triple-quoted string via a function call, the comment
    is placed after '(' and the triple-quote is moved to the next line so that it remains
    a proper Python comment rather than being embedded in string content.

    For other cases (assignments, bare strings), falls back to _merge_ty_ignore, which
    may embed the comment in the string; the caller's no-progress detection will then
    exclude the file.
    """
    raw_line = lines[idx]
    result = _find_unclosed_triple_quote_pos(raw_line)
    if result is None:
        lines[idx] = _merge_ty_ignore(raw_line=raw_line, codes=codes)
        return

    line = raw_line.rstrip("\n").rstrip("\r")
    eol = raw_line[len(line) :]
    code_part = line[: result.position]

    if code_part.rstrip().endswith("("):
        # Function call: place comment after ( and move triple-quote to next line.
        # Strip any stale ty:ignore that landed inside the string on a prior pass.
        triple_content = _TY_IGNORE_RE.sub("", line[result.position :]).rstrip()
        if not triple_content:
            triple_content = result.quote

        all_codes = sorted(codes)
        new_ignore = f"# ty: ignore[{', '.join(all_codes)}]"
        lines[idx] = f"{code_part.rstrip()}  {new_ignore}{eol}"
        base_indent = len(line) - len(line.lstrip())
        new_indent = " " * (base_indent + 4)
        lines.insert(idx + 1, f"{new_indent}{triple_content}{eol}")
        return

    # Assignment / other: fall back to regular merge.
    lines[idx] = _merge_ty_ignore(raw_line=raw_line, codes=codes)


def _merge_ty_ignore(*, raw_line: str, codes: ErrorCodes) -> str:
    """Merge ty ignore codes into a source line.

    - `unused-ignore-comment` in codes → remove the existing # ty: ignore entirely;
      any other codes in the same set are added fresh (the old comment is discarded).
    - All other codes → add to / merge with existing # ty: ignore[...].
    """
    line = raw_line.rstrip("\n").rstrip("\r")
    eol = raw_line[len(line) :]

    remove_existing = _UNUSED_IGNORE_CODE in codes
    actual_codes = codes - {_UNUSED_IGNORE_CODE}

    ignore_match = _TY_IGNORE_RE.search(line)
    if ignore_match:
        code_part = line[: ignore_match.start()].rstrip()
        if not remove_existing:
            existing_raw = ignore_match.group(1) or ""
            existing_codes = {c.strip() for c in existing_raw.split(",") if c.strip()}
            actual_codes = actual_codes | existing_codes
    else:
        code_part = line

    if not actual_codes:
        return f"{code_part}{eol}"

    all_codes = sorted(actual_codes)
    new_ignore = f"# ty: ignore[{', '.join(all_codes)}]"
    return f"{code_part}  {new_ignore}{eol}"
