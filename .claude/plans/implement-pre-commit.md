# Plan: Implement PreCommitBoost

## Context
`PreCommitBoost` is already registered in the default boost list but is a stub that raises `BoostSkippedError("Not implemented")`. This plan implements it fully. The boost should:
- Write `.pre-commit-config.yaml` based on what tooling has been configured (ruff/mypy/uv via the justfile)
- Add `pre-commit` as a dev dependency
- Run `pre-commit install` to activate the hooks

The project's own `.pre-commit-config.yaml` is the reference for content and hook structure.

## Key Design Decisions

**Registry reorder:** JustfileBoost must run before PreCommitBoost (currently it runs after). PreCommitBoost reads the justfile to discover which local hooks to include (`check-ruff`, `check-mypy`, `check-lock`). If it runs before JustfileBoost, those recipes don't exist yet.

**Local hooks are conditional:** Only include a local hook if the corresponding justfile recipe exists. JustfileBoost creates `check-ruff` (if ruff configured) and `check-mypy` (if mypy configured) but does NOT create `check-lock`. So `check-uv-lock` only appears in repos that already have a `check-lock` recipe.

**YAML as string constants:** No yaml library needed — the config is fixed in structure.

**`pre-commit install` uses `uv run`:** Since pre-commit is added with `--no-sync`, `uv run pre-commit install` triggers an implicit sync to install it, then runs it. This is consistent with how the project's own `install-dev` recipe works.

**No explicit `git.add()` or `git.commit()` in apply():** The booster calls `repo_controller.commit()` after `apply()` returns, which does `git add -A`. `write_file()` only writes the file without staging. `uv add --no-sync` modifies `pyproject.toml` + `uv.lock` (picked up by `git add -A`). `pre-commit install` modifies `.git/hooks/` which is not tracked.

## Files to Modify

### 1. `pimp_my_repo/core/registry.py`
Swap order of `JustfileBoost` and `PreCommitBoost`:
```python
_DEFAULT_BOOSTS = [GitignoreBoost, UvBoost, RuffBoost, MypyBoost, JustfileBoost, PreCommitBoost]
```

### 2. `pimp_my_repo/core/boosts/pre_commit.py` — Full implementation

**Imports:**
```python
import re
from pathlib import Path
from loguru import logger
from pimp_my_repo.core.boosts.base import Boost, BoostSkippedError
from pimp_my_repo.core.tools.pyproject import PyProjectNotFoundError
from pimp_my_repo.core.tools.uv import UvNotFoundError
```

**Constants (YAML content strings):**
```python
_CONFIG_FILE = ".pre-commit-config.yaml"
_STANDARD_HOOKS = """\
# See https://pre-commit.com for more information
# See https://pre-commit.com/hooks.html for more hooks
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
"""
_LOCAL_HOOKS_HEADER = "  - repo: local\n    hooks:\n"
_HOOK_CHECK_LOCK = '      - id: check-uv-lock\n        name: check uv lock\n        entry: "just check-lock"\n        language: system\n        pass_filenames: false\n'
_HOOK_CHECK_RUFF = '      - id: check-ruff\n        name: check ruff standard\n        entry: "just check-ruff"\n        language: system\n        pass_filenames: false\n'
_HOOK_CHECK_MYPY = '      - id: check-mypy\n        name: check mypy typing\n        entry: "just check-mypy"\n        language: system\n        pass_filenames: false\n'
```

**`apply()` logic:**
1. Idempotency guard: if `(self.repo_path / _CONFIG_FILE).exists()` → `BoostSkippedError("pre-commit already configured")`
2. Check prerequisites: `self.uv.verify_present()` (catch `UvNotFoundError` → `BoostSkippedError`), `self.pyproject.verify_present()` (catch `PyProjectNotFoundError` → `BoostSkippedError`)
3. `self.uv.add_package("pre-commit", dev=True)`
4. `justfile_recipes = _get_justfile_recipes(self.repo_path)` → build config
5. `self.git.write_file(_CONFIG_FILE, config_content)`
6. `self.uv.exec("run", "pre-commit", "install")`
7. Log: `logger.info("pre-commit hooks installed")`

**Private helpers:**
- `_get_justfile_recipes(repo_path: Path) -> set[str]`: reads justfile, returns set of recipe names via regex `re.match(r"^([a-zA-Z0-9][a-zA-Z0-9_-]*)", line)` (same logic as `justfile._get_existing_recipes` but private here to avoid cross-module private import)
- `_build_config(justfile_recipes: set[str]) -> str`: builds YAML string — always starts with `_STANDARD_HOOKS`, appends `_LOCAL_HOOKS_HEADER` + local hooks if any of `check-lock`, `check-ruff`, `check-mypy` are present

### 3. `tests/test_pre_commit_boost.py` — New file

**Fixtures:**
- `pre_commit_boost(boost_tools)` → `PreCommitBoost(boost_tools)` (bare, no pyproject)
- `pre_commit_boost_with_pyproject(boost_tools, mock_repo)` → writes `pyproject.toml`, returns `PreCommitBoost(boost_tools)`
- `patched_pre_commit_apply` dataclass fixture: patches `uv.add_package` and `uv.exec` on `pre_commit_boost_with_pyproject`

**Tests:**
- `test_skips_when_config_already_exists` — write file first, assert `BoostSkippedError`
- `test_skips_when_uv_not_present` — patch `verify_present` to raise `UvNotFoundError`
- `test_skips_when_no_pyproject` — patch `verify_present` to pass, no pyproject file
- `test_happy_path_no_justfile_writes_standard_hooks_only` — no justfile, assert standard hooks written, no local section
- `test_happy_path_with_ruff_and_mypy_recipes` — justfile has both, assert local hooks present
- `test_includes_only_check_ruff_when_only_ruff_recipe_present`
- `test_includes_check_lock_when_recipe_present`
- `test_calls_pre_commit_install` — assert `mock_uv_exec.assert_called_once_with("run", "pre-commit", "install")`
- `test_adds_pre_commit_as_dev_dependency` — assert `mock_add_package.assert_called_once_with("pre-commit", dev=True)`
- `test_commit_message` — `"✨ Add pre-commit hooks"`
- `test_get_name` — `"precommit"`

### 4. `tests/fixtures/pre-commit/` — New E2E fixture
Mirror the `minimal-package` fixture:
- `pyproject.toml` with `[project]` and `[build-system]`
- `src/pre_commit_fixture/__init__.py`
- `src/pre_commit_fixture/main.py` (simple function)

### 5. `tests/test_e2e_local.py`
Add `"pre-commit"` to `_FIXTURES` list.

## Verification

After implementation:
1. `just lint` — must pass
2. `just test` — all unit tests must pass
3. `just test-e2e-local pre-commit` — E2E must run cleanly and produce a `.pre-commit-config.yaml` in the fixture repo
