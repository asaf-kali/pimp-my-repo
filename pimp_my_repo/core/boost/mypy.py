"""Mypy boost implementation."""

import re
import subprocess
from typing import Any, NamedTuple

from loguru import logger
from tomlkit import TOMLDocument, dumps, loads, table

from pimp_my_repo.core.boost.base import Boost, BoostSkippedError
from pimp_my_repo.core.git import COMMIT_AUTHOR

_MAX_MYPY_ITERATIONS = 3


class ViolationLocation(NamedTuple):
    """A single violation location: file path and line number."""

    filepath: str
    lineno: int


type ErrorCodes = set[str]
type ViolationsByLocation = dict[ViolationLocation, ErrorCodes]
type LineViolations = dict[int, ErrorCodes]
type ViolationsByFile = dict[str, LineViolations]


def _merge_type_ignore(*, raw_line: str, codes: ErrorCodes) -> str:
    """Merge type: ignore codes into a source line, preserving or creating the comment."""
    line = raw_line.rstrip("\n").rstrip("\r")
    eol = raw_line[len(line) :]

    ignore_match = re.search(r"#\s*type:\s*ignore(?:\[([^\]]*)\])?", line)
    if not ignore_match:
        return f"{line}  # type: ignore[{', '.join(sorted(codes))}]{eol}"

    existing_str = ignore_match.group(1) or ""
    existing = {c.strip() for c in existing_str.split(",") if c.strip()}
    all_codes = existing | codes
    new_ignore = f"# type: ignore[{', '.join(sorted(all_codes))}]"
    merged = re.sub(r"#\s*type:\s*ignore(?:\[([^\]]*)\])?", new_ignore, line)
    return f"{merged}{eol}"


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

    def _run_mypy(self) -> subprocess.CompletedProcess[str]:
        return self._run_uv("run", "mypy", ".", check=False)

    def _read_pyproject(self) -> TOMLDocument:
        pyproject_path = self.repo_path / "pyproject.toml"
        with pyproject_path.open(encoding="utf-8") as f:
            return loads(f.read())

    def _write_pyproject(self, data: TOMLDocument) -> None:
        pyproject_path = self.repo_path / "pyproject.toml"
        with pyproject_path.open("w", encoding="utf-8") as f:
            f.write(dumps(data))

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
        """Parse mypy output into {ViolationLocation: {error_codes}}."""
        violations: ViolationsByLocation = {}
        for line in output.splitlines():
            match = re.match(r"^(.+?):(\d+):\s+error:.*?\[([^\]]+)\]\s*$", line)
            if not match:
                continue
            key = ViolationLocation(filepath=match.group(1), lineno=int(match.group(2)))
            violations.setdefault(key, set()).add(match.group(3))
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
            lines[idx] = _merge_type_ignore(raw_line=lines[idx], codes=codes)

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
        return True

    def _configure_mypy(self) -> None:
        self._add_mypy()
        logger.info("Configuring [tool.mypy] strict = true in pyproject.toml...")
        pyproject_data = self._read_pyproject()
        pyproject_data = self._ensure_mypy_config(pyproject_data)
        self._write_pyproject(pyproject_data)
        self._commit_config()

    def _commit_config(self) -> None:
        self._run_git("add", "-A")
        if not self._run_git("status", "--porcelain", check=False).stdout.strip():
            return
        self._run_git("commit", "--author", COMMIT_AUTHOR, "--no-verify", "-m", "🔧 Configure mypy with strict mode")
        logger.info("Committed mypy configuration")

    def _add_mypy(self) -> None:
        if self._is_package_in_deps("mypy"):
            logger.info("mypy already in dependencies, skipping uv add")
            return
        logger.info("Adding mypy dev dependency...")
        try:
            self._run_uv("add", "--dev", "mypy")
        except subprocess.CalledProcessError:
            logger.warning("uv add failed, editing pyproject.toml directly")
            self._add_dep_to_pyproject("dev", "mypy")
            self._run_uv("lock", check=False)

    def _verify_pyproject_present(self) -> None:
        if not (self.repo_path / "pyproject.toml").exists():
            msg = "No pyproject.toml found"
            raise BoostSkippedError(msg)

    def _verify_uv_present(self) -> None:
        try:
            result = self._run_uv("--version", check=False)
            if result.returncode != 0:
                msg = "uv is not available"
                raise BoostSkippedError(msg)
        except (FileNotFoundError, OSError) as e:
            msg = "uv is not installed"
            raise BoostSkippedError(msg) from e

    def commit_message(self) -> str:
        """Generate commit message for Mypy boost."""
        return "✅ Silence mypy violations"
