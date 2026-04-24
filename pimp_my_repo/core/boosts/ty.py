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


class ViolationLocation(NamedTuple):
    """A single violation location: file path and line number."""

    filepath: str
    lineno: int


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
        new_paths = sorted(paths - set(existing))
        if not new_paths:
            return
        logger.info(f"Excluding {len(new_paths)} unreadable file(s) from ty: {new_paths}")
        updated = array()
        updated.extend(existing + new_paths)
        src_section["exclude"] = updated
        self.pyproject.write(data)

    def _apply_ty_ignores(self, violations: ViolationsByLocation) -> None:
        """Insert, merge, or remove # ty: ignore[codes] on each violating line."""
        by_file: ViolationsByFile = {}
        for location, codes in violations.items():
            by_file.setdefault(location.filepath, {})[location.lineno] = codes

        for filepath, line_violations in by_file.items():
            self._apply_ty_ignores_to_file(filepath=filepath, line_violations=line_violations)

    def _apply_ty_ignores_to_file(self, *, filepath: str, line_violations: LineViolations) -> None:
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
                lines.insert(0, f"# ty: ignore[{', '.join(sorted(codes))}]\n")
            else:
                lines[idx] = _merge_ty_ignore(raw_line=lines[idx], codes=codes)

        logger.trace(f"Writing 'ty: ignore' comments to {filepath} in lines: {sorted(line_violations.keys())}")
        full_path.write_text("".join(lines), encoding="utf-8")

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
        if violations:
            logger.info(f"Found {len(violations)} violations, applying ty: ignore comments...")
            self._apply_ty_ignores(violations)
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
