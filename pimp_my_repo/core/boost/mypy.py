"""Mypy boost implementation."""

import re
import subprocess
from typing import Any

from loguru import logger
from tomlkit import TOMLDocument, dumps, loads, table

from pimp_my_repo.core.boost.base import Boost
from pimp_my_repo.core.git import COMMIT_AUTHOR

_MAX_MYPY_ITERATIONS = 3


class MypyBoost(Boost):
    """Boost for integrating Mypy type checker in strict mode."""

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

    def _parse_violations(self, output: str) -> dict[tuple[str, int], set[str]]:
        """Parse mypy output into {(filepath, lineno): {error_codes}}."""
        violations: dict[tuple[str, int], set[str]] = {}
        for line in output.splitlines():
            match = re.match(r"^(.+?):(\d+):\s+error:.*?\[([^\]]+)\]\s*$", line)
            if match:
                filepath = match.group(1)
                lineno = int(match.group(2))
                code = match.group(3)
                key = (filepath, lineno)
                if key not in violations:
                    violations[key] = set()
                violations[key].add(code)
        return violations

    def _apply_type_ignores(self, violations: dict[tuple[str, int], set[str]]) -> None:
        """Insert or merge # type: ignore[codes] on each violating line."""
        by_file: dict[str, dict[int, set[str]]] = {}
        for (filepath, lineno), codes in violations.items():
            by_file.setdefault(filepath, {})[lineno] = codes

        for filepath, line_violations in by_file.items():
            full_path = self.repo_path / filepath
            if not full_path.exists():
                logger.warning(f"File not found, skipping: {full_path}")
                continue

            lines = full_path.read_text(encoding="utf-8").splitlines(keepends=True)
            for lineno, codes in sorted(line_violations.items()):
                idx = lineno - 1
                if idx >= len(lines):
                    continue
                raw = lines[idx]
                line = raw.rstrip("\n").rstrip("\r")
                eol = raw[len(line) :]

                ignore_match = re.search(r"#\s*type:\s*ignore(?:\[([^\]]*)\])?", line)
                if ignore_match:
                    existing_str = ignore_match.group(1) or ""
                    existing = {c.strip() for c in existing_str.split(",") if c.strip()}
                    all_codes = existing | codes
                    new_ignore = f"# type: ignore[{', '.join(sorted(all_codes))}]"
                    line = re.sub(r"#\s*type:\s*ignore(?:\[([^\]]*)\])?", new_ignore, line)
                else:
                    line = f"{line}  # type: ignore[{', '.join(sorted(codes))}]"

                lines[idx] = line + eol

            full_path.write_text("".join(lines), encoding="utf-8")

    def check_preconditions(self) -> bool:
        """Verify prerequisites for applying Mypy boost."""
        try:
            result = self._run_uv("--version", check=False)
            if result.returncode != 0:
                logger.warning("uv is not available, skipping mypy boost")
                return False
        except FileNotFoundError, OSError:
            logger.warning("uv is not installed, skipping mypy boost")
            return False

        if not (self.repo_path / "pyproject.toml").exists():
            logger.warning("No pyproject.toml found, skipping mypy boost")
            return False

        return True

    def apply(self) -> None:
        """Add mypy, configure strict mode, commit, then suppress all violations."""
        # Phase 1: add mypy dep + configure strict mode
        logger.info("Adding mypy dev dependency...")
        self._run_uv("add", "--dev", "mypy")

        logger.info("Configuring [tool.mypy] strict = true in pyproject.toml...")
        pyproject_data = self._read_pyproject()
        pyproject_data = self._ensure_mypy_config(pyproject_data)
        self._write_pyproject(pyproject_data)

        self._run_git("add", "-A")
        if self._run_git("status", "--porcelain", check=False).stdout.strip():
            self._run_git(
                "commit", "--author", COMMIT_AUTHOR, "--no-verify", "-m", "🔧 Configure mypy with strict mode"
            )
            logger.info("Committed mypy configuration")

        # Phase 2: iteratively suppress violations
        for iteration in range(1, _MAX_MYPY_ITERATIONS + 1):
            logger.info(f"Running mypy (iteration {iteration}/{_MAX_MYPY_ITERATIONS})...")
            result = self._run_mypy()

            if result.returncode == 0:
                logger.info("mypy passed with no errors")
                break

            violations = self._parse_violations(result.stdout + result.stderr)
            if not violations:
                logger.info("No parseable violations found; stopping")
                break

            logger.info(f"Found {len(violations)} violations, applying type: ignore comments...")
            self._apply_type_ignores(violations)

    def verify(self) -> bool:
        """Verify mypy passes with strict mode."""
        result = self._run_mypy()
        if result.returncode == 0:
            logger.info("mypy verification passed")
            return True
        logger.warning(f"mypy verification failed:\n{result.stdout}")
        return False

    def commit_message(self) -> str:
        """Generate commit message for Mypy boost."""
        return "✅ Silence mypy violations"
