"""Ruff boost implementation."""

import re
import subprocess
from typing import Any, NamedTuple

from loguru import logger
from tomlkit import TOMLDocument, dumps, loads, table

from pimp_my_repo.core.boost.base import Boost, BoostSkippedError
from pimp_my_repo.core.git import COMMIT_AUTHOR

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

    def _run_uv(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        cmd = ["uv", *args]
        return subprocess.run(  # noqa: S603
            cmd,
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=check,
        )

    def _run_git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        cmd = ["git", *args]
        return subprocess.run(  # noqa: S603
            cmd,
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=check,
        )

    def _has_uncommitted_changes(self) -> bool:
        result = self._run_git("status", "--porcelain", check=False)
        return bool(result.stdout.strip())

    def _commit_if_changes(self, message: str) -> None:
        """Stage all changes and commit only if there is something to commit."""
        self._run_git("add", "-A")
        if self._has_uncommitted_changes():
            self._run_git("commit", "--author", COMMIT_AUTHOR, "--no-verify", "-m", message)
        else:
            logger.debug(f"Nothing to commit for: {message!r}")

    def _run_ruff_format(self) -> subprocess.CompletedProcess[str]:
        return self._run_uv("run", "ruff", "format", ".", check=False)

    def _run_ruff_check(self) -> subprocess.CompletedProcess[str]:
        return self._run_uv("run", "ruff", "check", ".", check=False)

    def _read_pyproject(self) -> TOMLDocument:
        pyproject_path = self.repo_path / "pyproject.toml"
        with pyproject_path.open(encoding="utf-8") as f:
            return loads(f.read())

    def _write_pyproject(self, data: TOMLDocument) -> None:
        pyproject_path = self.repo_path / "pyproject.toml"
        with pyproject_path.open("w", encoding="utf-8") as f:
            f.write(dumps(data))

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

    def _is_package_in_deps(self, package: str) -> bool:
        """Check if a package is already present in any dependency group in pyproject.toml."""
        try:
            data = self._read_pyproject()
        except (OSError, ValueError):  # fmt: skip
            return False
        package_lower = package.lower()
        for deps in data.get("dependency-groups", {}).values():
            for dep in deps:
                if isinstance(dep, str) and re.split(r"[>=<!@\s\[]", dep)[0].lower() == package_lower:
                    return True
        for deps in data.get("project", {}).get("optional-dependencies", {}).values():
            for dep in deps:
                if isinstance(dep, str) and re.split(r"[>=<!@\s\[]", dep)[0].lower() == package_lower:
                    return True
        return False

    def _add_dep_to_pyproject(self, group: str, package: str) -> None:
        """Add a package to a dependency group directly in pyproject.toml."""
        data = self._read_pyproject()
        if "dependency-groups" not in data:
            data["dependency-groups"] = table()
        dep_groups: Any = data["dependency-groups"]
        if group not in dep_groups:
            dep_groups[group] = [package]
        else:
            dep_groups[group].append(package)
        self._write_pyproject(data)

    def apply(self) -> None:
        """Add ruff, configure it, auto-format, then suppress all check violations."""
        try:
            result = self._run_uv("--version", check=False)
            if result.returncode != 0:
                msg = "uv is not available"
                raise BoostSkippedError(msg)
        except (FileNotFoundError, OSError) as e:
            msg = "uv is not installed"
            raise BoostSkippedError(msg) from e

        if not (self.repo_path / "pyproject.toml").exists():
            msg = "No pyproject.toml found"
            raise BoostSkippedError(msg)

        # Phase 1: add dep + configure
        if self._is_package_in_deps("ruff"):
            logger.info("ruff already in dependencies, skipping uv add")
        else:
            logger.info("Adding ruff dev dependency...")
            try:
                self._run_uv("add", "--group", "lint", "ruff")
            except subprocess.CalledProcessError:
                logger.warning("uv add failed, editing pyproject.toml directly")
                self._add_dep_to_pyproject("lint", "ruff")
                self._run_uv("lock", check=False)

        logger.info("Configuring [tool.ruff.lint] select = ['ALL'] in pyproject.toml...")
        pyproject_data = self._read_pyproject()
        pyproject_data = self._ensure_ruff_config(pyproject_data)
        self._write_pyproject(pyproject_data)

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
        return True

    def commit_message(self) -> str:
        """Generate commit message for Ruff boost."""
        return "✅ Silence ruff violations"
