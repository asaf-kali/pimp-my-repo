# CHANGELOG


## v0.4.8 (2026-04-09)

### 🖼️

- 🖼️ Handle mypy `--show-error-end` output format
  ([#49](https://github.com/asaf-kali/pimp-my-repo/pull/49),
  [`dcbb4cd`](https://github.com/asaf-kali/pimp-my-repo/commit/dcbb4cd4dd1e5d8691c03013ed675e9d42fb86f4))

When a target repo has `show_error_end = true` in its mypy config, mypy emits
  `path:line:col:endline:endcol: error:` instead of `path:line:col:`. The extra colon-number
  segments broke all four location regexes: _MYPY_LINE_START_RE didn't match, causing errors to fall
  into Category 2 (uncoded files) with a corrupted path that included the column numbers. No type:
  ignore comments were placed and the boost stalled.

Fix: replace `(?::\d+)?` with `(?::\d+)*` in the three `path:line` regexes

and use `(?:(?::\d+)+)?` in _MYPY_ANY_ERROR_RE so any number of trailing colon-number segments (col,
  col:endline:endcol, etc.) are consumed correctly.

https://claude.ai/code/session_01L3VUA2nZbrxiPzWicuBrNH

Co-authored-by: Claude <noreply@anthropic.com>


## v0.4.7 (2026-04-09)

### 🌴

- 🌴 Code quality fixes and UX improvements
  ([#48](https://github.com/asaf-kali/pimp-my-repo/pull/48),
  [`980f4a8`](https://github.com/asaf-kali/pimp-my-repo/commit/980f4a84dd828907a1a10d07a9ba47cb470b2d4b))

* fix: replace bare except with except BaseException in git revert context

https://claude.ai/code/session_01L3VUA2nZbrxiPzWicuBrNH

* refactor: remove unused RunResult model from result.py

BoostRunResult in runner.py is the actual result type used throughout the codebase. RunResult was
  dead code with no references.

* feat: add --branch flag and improve failure UX

- Add --branch/-b CLI option to customize the git branch name (default remains feat/pmr, threaded
  through runner → booster → init_pmr) - Show each failed boost's error message in the terminal
  summary, not just in the log file - Print the baseline note even when some boosts failed (raised
  Exit(1) after the note instead of inside _print_summary) - Add tests for --branch forwarding and
  error detail display

---------

Co-authored-by: Claude <noreply@anthropic.com>


## v0.4.6 (2026-04-08)

### Other

- 🎡 Add post-run comment ([#46](https://github.com/asaf-kali/pimp-my-repo/pull/46),
  [`e3a1b6f`](https://github.com/asaf-kali/pimp-my-repo/commit/e3a1b6f9816918fb132a5a344f0f7f583bb9eb5f))

### 🐛

- 🐛 Mypy boost stability fixes ([#47](https://github.com/asaf-kali/pimp-my-repo/pull/47),
  [`a89c037`](https://github.com/asaf-kali/pimp-my-repo/commit/a89c0372832281ef351b8a9615e24128bfb33cdd))

* Logging fixes

* 🐛 Fix mypy parsing: single-pass, keep syntax-file violations, remove parent-dir escalation

- Rewrite _parse_mypy_output as true single-pass: each line falls into exactly one category
  (diagnostic, no-line-number error, invalid pkg name, or summary). Remove separate
  _collect_no_line_number_errors pass and raw_output parameter. - Stop stripping non-syntax
  violations from syntax-error files. These can still be suppressed inline with type: ignore
  comments, which matters when mypy checks the file via import following (exclude only prevents
  discovery, not import following). - Remove parent-dir escalation in _apply_syntax_exclusions — it
  didn't help for import-following cases and caused confusing behavior. - Fix _normalize_mypy_output
  to preserve no-line-number error lines and invalid package name messages as separate entries. -
  Use multiline tomlkit arrays for mypy exclude lists. - Add trace/debug logging for parse results,
  raw output, and exclusion decisions.


## v0.4.5 (2026-04-07)

### 🐛

- 🐛 Raise only for truly unhandled mypy output; stop gracefully on exhausted exclusions
  ([#45](https://github.com/asaf-kali/pimp-my-repo/pull/45),
  [`89aa164`](https://github.com/asaf-kali/pimp-my-repo/commit/89aa164cc0685b8c3518877067d742b68a4e1b7c))

When all file/dir exclusions were exhausted (e.g. syntax file excluded at both file and parent-dir
  level), violations were stripped and the boost raised a misleading RuntimeError showing raw_output
  that contained normal coded violations.

Fix: only raise RuntimeError when `unhandled_lines` is non-empty (lines that matched no known
  pattern). When everything was parsed but no further exclusion is possible, log a warning and stop
  gracefully instead.

Also extracted the per-line loop body in `_parse_mypy_output` into small helpers
  (`_apply_note_line`, `_apply_coded_error_line`, `_apply_diagnostic_line`,
  `_collect_no_line_number_errors`) and applied early-return style throughout.

Co-authored-by: Claude Sonnet 4.6 <noreply@anthropic.com>


## v0.4.4 (2026-04-07)

### 🏗️

- 🏗️ Refactor mypy output parsing into a single-pass _parse_mypy_output
  ([#44](https://github.com/asaf-kali/pimp-my-repo/pull/44),
  [`eebe35f`](https://github.com/asaf-kali/pimp-my-repo/commit/eebe35f0653b1eea2b138c6c6525d27f52ef9a8c))


## v0.4.3 (2026-04-06)

### 🐛

- 🐛 Fail on unparsable mypy output; rename space-named dirs
  ([#43](https://github.com/asaf-kali/pimp-my-repo/pull/43),
  [`f8f3f61`](https://github.com/asaf-kali/pimp-my-repo/commit/f8f3f610c40c20ddc9516a50b3b0207c690afcc2))

- Raise RuntimeError when mypy returns non-zero but output cannot be parsed or handled, instead of
  silently treating as success - Fix _MYPY_INVALID_PKG_NAME_RE to match directory names containing
  spaces (was \S+, now .+) - Rename directories with spaces in their names (replace space →
  underscore) instead of excluding them from mypy - Update and add tests covering all new behaviors

Co-authored-by: Claude Sonnet 4.6 <noreply@anthropic.com>


## v0.4.2 (2026-04-03)

### 🐛

- 🐛 JustfileBoost fixes; other infra adjustments
  ([#42](https://github.com/asaf-kali/pimp-my-repo/pull/42),
  [`ad6aebc`](https://github.com/asaf-kali/pimp-my-repo/commit/ad6aebc603b344d6daa2cdfec2c3da1173ec487d))

* 🐛 Add check-lock recipe to JustfileBoost to enable check-uv-lock pre-commit hook

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

* Logging fixes

* Adjust pre-commit boost logs and structure

* Move type defs

* Typing fixes

* noqa rule fixes

* Edit CLAUDE.md

* Add run-checks command

* Move CLAUDE.md

---------

Co-authored-by: Claude Sonnet 4.6 <noreply@anthropic.com>


## v0.4.1 (2026-04-02)

### Other

- ✅ Improve unit test coverage ([#40](https://github.com/asaf-kali/pimp-my-repo/pull/40),
  [`df56a6a`](https://github.com/asaf-kali/pimp-my-repo/commit/df56a6a4daed203f3eac9b1a3c576debd48713f2))

* ✅ Improve unit test coverage

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

* 🔧 Migrate test results upload to codecov-action@v5

* ⚡ Fix slow uv apply tests by using patched_uv_apply fixture

All apply() tests now mock subprocess calls (uv exec, exec_uvx, add_from_requirements,
  resolve_requires_python) via the patched_uv_apply fixture, preventing real uv/pip invocations and
  keeping tests fast.

---------

Co-authored-by: Claude Sonnet 4.6 <noreply@anthropic.com>

### 🖼️

- 🖼️ Implement pre-commit hooks boost ([#41](https://github.com/asaf-kali/pimp-my-repo/pull/41),
  [`4147bf7`](https://github.com/asaf-kali/pimp-my-repo/commit/4147bf7ce2296aa3bc8437e203901c4bc0b539be))

* Add implementation plan for pre-commit hooks boost

* 🎁 Implement pre-commit hooks boost

* ✅ Assert pre-commit config and hooks pass in e2e tests

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

* 🐛 Run pre-commit hooks once in apply() to pre-fix violations before commit

* 🐛 Only assert pre-commit hooks for PMR-generated configs

---------

Co-authored-by: Claude Sonnet 4.6 <noreply@anthropic.com>


## v0.4.0 (2026-04-02)

### 🎆

- 🎆 Add Codecov integration ([#39](https://github.com/asaf-kali/pimp-my-repo/pull/39),
  [`d381de1`](https://github.com/asaf-kali/pimp-my-repo/commit/d381de11db67a2c9f28fe63511cd686adb2dd36a))

* 📊 Add Codecov integration

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

* 📊 Add Codecov test analytics

* 🧹 Remove unused coverage percentage step

* 🔧 Pass secrets to reusable checks workflow

---------

Co-authored-by: Claude Sonnet 4.6 <noreply@anthropic.com>


## v0.3.10 (2026-04-02)

### 📝

- 📝 Logging fixes ([#38](https://github.com/asaf-kali/pimp-my-repo/pull/38),
  [`6e71776`](https://github.com/asaf-kali/pimp-my-repo/commit/6e717769cb0965017cd6edfdb918a545d3f09fff))

* 🪵 Add logging improvements

- Expose package version in startup log message - Add finish log after all boosts complete - Log git
  status output in is_clean for better visibility - Widen e2e separator line

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

* ♻️ Refactor RepositoryController: eliminate duplicate git add calls

- Use self.add() in add_and_commit, commit, and reset_tracking instead of calling
  self.execute("add", ...) directly - Extract _get_stripped_output() to deduplicate the
  execute→validate→strip pattern in get_origin_url and get_current_commit_sha

* Add new boost skill

---------

Co-authored-by: Claude Sonnet 4.6 <noreply@anthropic.com>


## v0.3.9 (2026-04-01)

### Other

- ✅ Add httpie to e2e tests; support setup.cfg migration
  ([`343f31b`](https://github.com/asaf-kali/pimp-my-repo/commit/343f31b0065271d50ed87598a0e4cfa138ff34f4))

- Migrate setup.cfg + setup.py projects to pyproject.toml manually (migrate-to-uv v0.11.0 does not
  support setup.cfg) - Handle attr:/file: dynamic version references with a static placeholder - Add
  hatchling build-system to migrated pyproject.toml - Fall back to version search when lock fails
  with pre-existing requires-python - Add setup-cfg-package fixture to cover this migration path -
  Exclude tests/fixtures/ from top-level ruff discovery (fixes INP001)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

- 🧠 Update support-repo skill: fixture-first workflow, just test-e2e-local
  ([#34](https://github.com/asaf-kali/pimp-my-repo/pull/34),
  [`21d66b6`](https://github.com/asaf-kali/pimp-my-repo/commit/21d66b6a4010ab4ae66466c2a3179ebb4db324cd))

Co-authored-by: Claude Sonnet 4.6 <noreply@anthropic.com>

### 🐛

- 🐛 Upper bound linters ([#37](https://github.com/asaf-kali/pimp-my-repo/pull/37),
  [`c0d3339`](https://github.com/asaf-kali/pimp-my-repo/commit/c0d3339ac3aea72a1b1efba9177161c6a8df6891))

* User shorter SHA for e2e tests

* Upgrade dependencies

* ✨ Make rev optional in just test-e2e

When rev is omitted, skip the git checkout and use the repo's default branch HEAD. Test logging
  fixes.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

* 📌 Pin ruff<0.16 and mypy<1.20 in boosts

---------

Co-authored-by: Claude Sonnet 4.6 <noreply@anthropic.com>


## v0.3.8 (2026-03-31)

### 🛠️

- 🛠️ Add fixture-based local e2e tests; unify e2e infrastructure
  ([#33](https://github.com/asaf-kali/pimp-my-repo/pull/33),
  [`0a653c0`](https://github.com/asaf-kali/pimp-my-repo/commit/0a653c07fd2d65d5d6cfc7bc059a2f49d4f14ab7))

- Add tests/fixtures/ with minimal-package as the first fixture - Add tests/e2e_utils.py with shared
  setup/run/verify helpers - Add tests/test_e2e_fixtures.py: fast local fixture tests, run on every
  PR - Add tests/test_e2e_remote.py: replaces scripts/test_e2e.py, driven by --e2e-url / --e2e-rev
  pytest CLI options - Add pytest_addoption + e2e_url/e2e_rev fixtures to conftest.py - Exclude
  tests/fixtures/ from ruff and mypy - Update justfile: test-e2e-local (new), test-e2e url rev ->
  pytest - Update CI: add test-e2e-local job (every PR); test-e2e matrix calls just test-e2e -
  Remove scripts/test_e2e.py (superseded)

Co-authored-by: Claude Sonnet 4.6 <noreply@anthropic.com>


## v0.3.7 (2026-03-30)

### 📝

- 📝 Minor logging fixes ([#31](https://github.com/asaf-kali/pimp-my-repo/pull/31),
  [`855edc4`](https://github.com/asaf-kali/pimp-my-repo/commit/855edc48e1df2c5739e54c11f878bf2ed7c49041))


## v0.3.6 (2026-03-30)

### ✨

- ✨ Add scikit-learn e2e support; minor fixes; fix RUF100 oscillation
  ([#30](https://github.com/asaf-kali/pimp-my-repo/pull/30),
  [`cce6723`](https://github.com/asaf-kali/pimp-my-repo/commit/cce6723a55ab12eba76b97d377af60a128b7a4f6))

* 🔧 Address review: deduplicate native backend check, fix level casing, add comment

- _ensure_uv_config_present: compute _has_native_build_backend() once, pass is_native flag to
  _ensure_uv_config and _is_installable_package to avoid reading pyproject.toml twice per boost run
  - log_output call site in ruff: use "TRACE" (uppercase) to match logger.log() convention - Add
  inline comment explaining version = "0.0.0" is a uv lockfile placeholder

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

* ✅ Add scikit-learn to e2e tests; fix RUF100 oscillation on file-level noqa

Add RUF100 to _UNSUPPRESSIBLE_CODES and to the ruff ignore list. File-level `# ruff: noqa: CODE`
  directives cause RUF100 violations that inline `# noqa: RUF100` cannot suppress (the directive
  remains unused), creating an oscillation loop across iterations.

---------

Co-authored-by: Claude Sonnet 4.6 <noreply@anthropic.com>


## v0.3.5 (2026-03-30)

### Other

- 🔧 Include CI e2e logs in artifcats ([#28](https://github.com/asaf-kali/pimp-my-repo/pull/28),
  [`a136d09`](https://github.com/asaf-kali/pimp-my-repo/commit/a136d09ac839a22d984ee70ee4f531916c2863a7))

### ✨

- ✨ Support native build backends (e.g. pandas/mesonpy)
  ([#29](https://github.com/asaf-kali/pimp-my-repo/pull/29),
  [`67b02e2`](https://github.com/asaf-kali/pimp-my-repo/commit/67b02e2516fcc3fab86f5a9cdeffa81a78900d33))

* ✨ Support native build backends (e.g. pandas/mesonpy)

For projects using non-pure-Python build backends (mesonpy, scikit-build-core, maturin), uv cannot
  build the project without the native toolchain. This PR fixes PMR to handle these projects by:

- Detecting native build backends via `[build-system] build-backend` - Setting `[tool.uv] package =
  false` to skip local-package installation - Removing `optional-dependencies` (avoids circular
  transitive deps, e.g. fastparquet → pandas) - Replacing dynamic `version` with a static
  placeholder `0.0.0` (avoids metadata build) - Always log command stderr/stdout at DEBUG level on
  failure (previously silent) - Add pandas to CI e2e test matrix

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

* 🔧 Return CommandResult dataclass from run_command, control logging per caller

- Add CommandResult dataclass (cmd, returncode, stdout, stderr) with output property and
  log_output() method - run_command gains log_on_error (default True); when False, only logs exit
  code - UvController.exec/exec_uvx pass log_on_error through - Ruff
  _run_ruff_check/_run_ruff_format use log_on_error=False (output is huge) - Mypy _run_type_checker
  uses log_on_error=False (output is huge) - On ruff JSON parse failure, log output at TRACE (not
  warning)

* 🔧 Pass CommandResult to _handle_failure/_log_failure, add type hints

* 🔧 Remove get_output(), log both streams, use stdout for python --version

- Remove CommandResult.get_output() — the "stderr or stdout" logic silently discards one stream;
  callers now access .stdout/.stderr directly - log_output() logs stdout and stderr as separate
  labelled lines - python_version: use result.stdout directly (python --version → stdout in py3)

---------

Co-authored-by: Claude Sonnet 4.6 <noreply@anthropic.com>


## v0.3.4 (2026-03-29)

### 🐛

- 🐛 Pass --skip-lock to migrate-to-uv, fix duplicate requirements file handling
  ([#27](https://github.com/asaf-kali/pimp-my-repo/pull/27),
  [`283696b`](https://github.com/asaf-kali/pimp-my-repo/commit/283696bfe111919810b378b8bc86a24c5b324651))

* 🐛 Pass --skip-lock to migrate-to-uv; add coursist to e2e tests

migrate-to-uv was running `uv lock` internally before requires-python was set, defaulting to the
  current Python (3.14). Old packages with no pre-built wheel (e.g. django-allauth==0.42.0) couldn't
  be built from source with modern setuptools, causing the UV boost to fail. --skip-lock delegates
  locking entirely to _lock_with_requires_python(), which detects the right Python version first.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

* Add support-repo Claude skill

* Change full log print to before run

---------

Co-authored-by: Claude Sonnet 4.6 <noreply@anthropic.com>


## v0.3.3 (2026-03-29)

### ✨

- ✨ Add cavity-design repo to e2e tests with --rev pinning
  ([#26](https://github.com/asaf-kali/pimp-my-repo/pull/26),
  [`14cf000`](https://github.com/asaf-kali/pimp-my-repo/commit/14cf000df14ae5e8afe36cdfa25b9cda286e4f42))

* ✨ Add cavity-design repo to e2e tests with --rev pinning

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

* 🔒 Pin all e2e matrix repos to specific commits

* Semrel emoji change

---------

Co-authored-by: Claude Sonnet 4.6 <noreply@anthropic.com>


## v0.3.2 (2026-03-28)

### 🐛

- 🐛 Auto-detect requires-python in UV boost, multiple bug fixes
  ([#20](https://github.com/asaf-kali/pimp-my-repo/pull/20),
  [`d2d9e43`](https://github.com/asaf-kali/pimp-my-repo/commit/d2d9e4371c8e6142d9166b5bf5c9da6b31407fd6))

* ✨ Auto-detect requires-python in UV boost

Detection order: venv → uv.lock → vermin → (unset) Bumps minor version on uv lock conflict; removes
  constraint if all fail. Adds vermin >= 1.5 as a project dependency.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

* 🐛 Ensure venv is fully synced at end of UV boost

Add explicit `uv sync --all-groups` at the end of `apply()` to guarantee the venv is fully installed
  regardless of what happened in the retry loop. Add e2e validation using `uv sync --all-groups
  --check`.

* 🐛 Clear mypy cache before and after each type-check run

Extract _clear_mypy_cache() on BaseMypyBoost (clears .mypy_cache + .dmypy.json). Call it before and
  after every type-checker invocation so stale cache never affects results. For dmypy, clearing
  happens before kill (not after). Bump "no progress" log from info to warning. Add unit tests
  verifying cache-clear order for both MypyBoost and DmypyBoost.

* E2E script: support --rev flag

* 🐛 Fix sync_group wiping venv by using --group instead of --only-group

uv sync --only-group removes all packages not in that group. Switching to --group installs the group
  additively, preserving existing deps.

* 🧪 Fix e2e venv sync validation

- Flat layout (no src/) → package=false, no project-install noise in --check - Add requirements.txt
  with real dep (iniconfig) so sync_group bugs are detectable - Extract _assert_venv_fully_synced()
  helper, run it after both boost runs - Add loguru logging around sync check for better debugging

* 🔧 Address PR review issues

* ✨ Add upper bound to pre-existing bare requires-python

If pyproject.toml already has requires-python = ">=x.y" (no upper bound), normalize it to
  ">=x.y,<x.(y+1)" before locking, consistent with how newly detected versions are written.

---------

Co-authored-by: Claude Sonnet 4.6 <noreply@anthropic.com>


## v0.3.1 (2026-03-28)

### Other

- ⬆️ Bump GitHub Actions to Node.js 24 compatible versions
  ([#24](https://github.com/asaf-kali/pimp-my-repo/pull/24),
  [`cc59bb8`](https://github.com/asaf-kali/pimp-my-repo/commit/cc59bb8329e611f3d74bb6da80a837b602cfec37))

- actions/checkout: v4 → v6 - actions/setup-python: v5 → v6 - astral-sh/setup-uv: v4 → v7 -
  extractions/setup-just: v2 → v3

Co-authored-by: Claude Sonnet 4.6 <noreply@anthropic.com>

### 🐛

- 🐛 Move publish job to ci.yml to fix PyPI trusted publishing
  ([#25](https://github.com/asaf-kali/pimp-my-repo/pull/25),
  [`e52f7c6`](https://github.com/asaf-kali/pimp-my-repo/commit/e52f7c6667cb07addaf5668988dd2f588af7e31b))

PyPI trusted publishing does not support reusable workflows — the publish step must live directly in
  the calling workflow. Move publish from delivery.yml to ci.yml and expose 'released' as a workflow
  output.

Co-authored-by: Claude Sonnet 4.6 <noreply@anthropic.com>


## v0.3.0 (2026-03-28)

### Other

- 🔨 CI fixes ([#23](https://github.com/asaf-kali/pimp-my-repo/pull/23),
  [`c325888`](https://github.com/asaf-kali/pimp-my-repo/commit/c3258884568fb0108711348a0f2b1e30ba745c18))

* .gitignore fix

* 🐛 Fix dashboard spamming CI logs

force_terminal=True caused Rich's Live display to emit cursor-movement escape codes at 10 Hz even in
  non-TTY environments (CI), reprinting the full dashboard as raw text on every refresh. Removing it
  lets Rich auto-detect the environment and disable timed refresh in CI.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

🐛 Fix branch name not interpolated in log messages

Loguru uses f-string / {} style formatting, not %s.

* 🔧 Allow e2e tests to run on manual workflow dispatch

🔧 Merge tests workflow into checks

🔧 Split release/publish into delivery workflow

---------

Co-authored-by: Claude Sonnet 4.6 <noreply@anthropic.com>

### ✨

- ✨ Implement JustfileBoost ([#22](https://github.com/asaf-kali/pimp-my-repo/pull/22),
  [`1525357`](https://github.com/asaf-kali/pimp-my-repo/commit/15253574003ccfe1ac718f018270a012d5762b33))

Add justfile generation to target repos with install, format, lint, check-ruff, and check-mypy
  recipes. Detects configured tools (ruff, mypy, pre-commit) and skips recipes already present in an
  existing justfile. Attempts to install just via platform-appropriate package manager if not found.

Co-authored-by: Claude Sonnet 4.6 <noreply@anthropic.com>


## v0.2.12 (2026-03-27)

### 🌴

- 🌴 Organize logs ([#19](https://github.com/asaf-kali/pimp-my-repo/pull/19),
  [`8eb4ee4`](https://github.com/asaf-kali/pimp-my-repo/commit/8eb4ee451cfd2af792b1237b590784fe64745202))

* Use loguru instead of internal logger

* ✨ Auto-log to file; remove --verbose

Always write a full log (level 0) to ~/.local/state/pmr/pmr-TIMESTAMP.log. The terminal dashboard
  stays at INFO only, keeping output clean.

- Add --no-log-file flag to disable file logging - Remove --verbose / -v (file covers that use case)
  - Format: [timestamp] [level] message [module] [file:line] - Print log path to console after run
  completes

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

* Add more verbose logs

* Sort out console

---------

Co-authored-by: Claude Sonnet 4.6 <noreply@anthropic.com>


## v0.2.11 (2026-03-27)

### 🐛

- 🐛 Fix multiple e2e failures ([#18](https://github.com/asaf-kali/pimp-my-repo/pull/18),
  [`a9ec332`](https://github.com/asaf-kali/pimp-my-repo/commit/a9ec332e8d2834ddd1b81e4a817b8fe7b983ddff))

* 🐛 Fix e2e failures: exit code, uv add, ruff silent pass, empty name, package detection

- cli/main.py: exit with code 1 when any boost fails (was silently exiting 0) - core/tools/uv.py:
  use --no-sync instead of --no-install-project in add_package / add_from_requirements_file to avoid
  compiling runtime deps during dependency add - core/boosts/ruff.py: raise RuntimeError when ruff
  check produces non-JSON output instead of silently stopping iterations as if all violations were
  suppressed - core/booster.py: catch RuntimeError in _run_boost_class alongside CalledProcessError
  - core/boosts/uv/uv.py: fix empty project name left by migrate-to-uv (name="" breaks uv run);
  detect package structure to set package=false for script/data-science repos that have no src/ or
  top-level __init__.py - scripts/test_e2e.py: use ruff format --check instead of ruff format in
  verification - tests: update test expectations to match corrected behaviour

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

* 🐛 Fix ruff/mypy boosts failing in CI: sync lint group before running tools

uv add --no-sync only updates pyproject.toml and the lockfile; it does not install anything.
  Subsequent uv run calls then try to sync the full environment (including the project build), which
  fails on projects without a clean build setup (no build-system, src/ layout without __init__.py,
  etc.).

Fix: explicitly sync only the lint dependency group before running ruff/mypy: uv sync
  --no-install-project --no-default-groups --group lint

Then run the tool with --no-sync so uv skips the redundant re-sync. Added UvController.sync_group()
  for this purpose.

* Add no-sync, rename method

* 🐛 Fix sync_group failing on repos with unbuildable main deps

Use --only-group instead of --no-default-groups --group when syncing a lint dependency group. The
  old flags still resolved and built the project's main dependencies (e.g. pillow from source),
  which fails when the host is missing system libs or only Python 3.14 wheels are available.
  --only-group skips all project deps entirely, installing just the target group.

Also fix 39 test errors caused by the previous rename of UvController.run → exec / run_uvx →
  exec_uvx: update all patch.object calls in the test fixtures to use the current method names.

---------

Co-authored-by: Claude Sonnet 4.6 <noreply@anthropic.com>


## v0.2.10 (2026-03-07)

### 🖼️

- 🖼️ Separate publish from release ([#17](https://github.com/asaf-kali/pimp-my-repo/pull/17),
  [`b93e38d`](https://github.com/asaf-kali/pimp-my-repo/commit/b93e38ddb18af19652432b36e21dd2305b595ae5))


## v0.2.9 (2026-03-07)

### 🖼️

- 🖼️ Fix CI release ([#16](https://github.com/asaf-kali/pimp-my-repo/pull/16),
  [`0597192`](https://github.com/asaf-kali/pimp-my-repo/commit/05971922a4f06e6e770183706098f9d390c1667e))


## v0.2.8 (2026-03-07)

### 🖼️

- 🖼️ Fix CI workflow structure ([#14](https://github.com/asaf-kali/pimp-my-repo/pull/14),
  [`8211864`](https://github.com/asaf-kali/pimp-my-repo/commit/82118644fba5c5d6e9260a9117e6b30d46aa073e))

- 🖼️ Simplify CI structure ([#15](https://github.com/asaf-kali/pimp-my-repo/pull/15),
  [`9f078e7`](https://github.com/asaf-kali/pimp-my-repo/commit/9f078e76555b3be816c565f36cf8fbf65887415e))


## v0.2.7 (2026-03-07)

### 🛠️

- 🛠️ Adjust UI, fix dmypy commit message ([#13](https://github.com/asaf-kali/pimp-my-repo/pull/13),
  [`0c28802`](https://github.com/asaf-kali/pimp-my-repo/commit/0c28802b321b9fa5ac9112085edcb71be068624a))

* Fix dmypy commit message

* UI adjustments


## v0.2.6 (2026-03-07)

### Other

- 🎡 CI fixes ([#11](https://github.com/asaf-kali/pimp-my-repo/pull/11),
  [`e074397`](https://github.com/asaf-kali/pimp-my-repo/commit/e074397e200ad035c369e11a9f81e5ce30098312))

* E2E config fix

* Adjust CI E2E tests

### 🌴

- 🌴 Mypy boost: increase coverage ([#12](https://github.com/asaf-kali/pimp-my-repo/pull/12),
  [`54bb93a`](https://github.com/asaf-kali/pimp-my-repo/commit/54bb93af120d6d495df44c2438dd4da15ecad81c))

* Justfile fixes

* UV boost - support more cases

* Handle invalid Python package names in mypy boost

Directories with hyphens (e.g. pyfiglet's fonts-standard/) are not valid Python package names. Mypy
  reports these as fatal errors (exit code 2) with no file/line context, so the existing violation
  parsers miss them.

Add _exclude_invalid_package_names() to detect these messages, find the matching directories under
  the repo root, and add them to [tool.mypy] exclude.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

* Fix mypy boost to handle pretty=true output format

When a project has `pretty = true` in [tool.mypy], mypy wraps long error lines across multiple
  lines. This breaks the per-line regex parser, causing the boost to see "No parseable violations
  found" and skip suppression.

Force `pretty = false` in the mypy config we write so error lines are always single-line and match
  _MYPY_ERROR_RE regardless of the project's prior config.

* Support mypy pretty=true output without overriding it

Previously we forced pretty=false in the mypy config to avoid wrapped lines breaking the per-line
  regex parser.

Now we normalize the output before parsing instead: - _normalize_mypy_output() joins continuation
  lines (pretty=true wraps long error messages across multiple lines) and skips indented
  source-context and caret lines added by pretty mode. - _MYPY_ERROR_RE drops the $ anchor so greedy
  .* finds the last [code] on a joined line even when a summary line is appended after the code. -
  Parsers for standalone non-path messages (invalid package names) still use raw_output to avoid
  losing lines that the joiner might merge with others.

Projects can now keep their preferred pretty=true setting and it is handled correctly through the
  normalization step.

---------

Co-authored-by: Claude Sonnet 4.6 <noreply@anthropic.com>


## v0.2.5 (2026-03-07)

### 🐛

- 🐛 Fixed mypy boost, adjust ruff boost structure
  ([#10](https://github.com/asaf-kali/pimp-my-repo/pull/10),
  [`f008da7`](https://github.com/asaf-kali/pimp-my-repo/commit/f008da7b5f103ed41f7d724eeec64b81a76e2561))

* README additions

* Add e2e tests

* Subprocess env vars fix

* Adjust ruff boost structure

* Log format fix

* Run dmypy instead of mypy

* Run both mypy and dmypy, refactor

* Mypy end of line removal fix

* mypy and dmypy tools disagree fix

* mypy converge fix

* Separate dmypy from mypy boost


## v0.2.4 (2026-03-06)

### 🏗️

- 🏗️ UI fixes, increase mypy stability ([#9](https://github.com/asaf-kali/pimp-my-repo/pull/9),
  [`814afdc`](https://github.com/asaf-kali/pimp-my-repo/commit/814afdc2b9a686f6d378779d2410e1c1041c34ec))

* Support syntax violations

* Minor refactoring

* 🐛 Exclude files with unsuppressable mypy errors

When mypy reports errors that can't be suppressed with type: ignore (syntax errors or no-code
  blocking errors like "source file found twice"), exclude those files in [tool.mypy] instead of
  looping indefinitely.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

* 🐛 Fix type: ignore placement for triple-quoted string openings

When mypy reports an error on a line that opens a multiline triple-quoted string (e.g. `x = """` or
  `func("""`), placing `# type: ignore[...]` after `"""` embeds it inside the string literal where
  mypy cannot see it.

Fix by detecting unclosed triple-quotes in `_place_type_ignore`: - Function call pattern `func("""`:
  split the line at `"""`, place the comment after `(`, and move the triple-quote to the next line.
  - Assignment pattern `x = """`: wrap the RHS with `()` by adding `(` on the opening line and `)`
  immediately after the closing `"""`.

Process violations in reverse line order so that line insertions do not shift the indices of
  not-yet-processed earlier violations.

* Auto commit

* Mypy: Bug: The mypy iteration loop failed to converge when a syntax-error (or
  uncoded-blocking-error) file persisted in mypy's output even after being added to pyproject.toml's
  exclude list. The stop condition checked not syntax_files — but syntax_files is derived from
  mypy's output, not from whether the exclusion was new. So if mypy kept reporting the same
  already-excluded file, syntax_files remained non-empty and the loop ran all 7 iterations doing
  nothing productive.

Fix (mypy.py): - _exclude_mypy_files now returns bool — True if new patterns were added, False if
  all were already present - _exclude_blocking_uncoded_errors likewise returns bool -
  _process_mypy_iteration uses these booleans (newly_excluded_syntax, newly_excluded_uncoded) in the
  stop condition instead of the raw sets

Tests added: test_stops_when_syntax_file_already_excluded and
  test_stops_when_uncoded_blocking_file_already_excluded — both verify the loop stops after exactly
  2 iterations (first iteration excludes the file, second finds no new progress and stops).

* UI refactor

* Mypy boost fixes

---------

Co-authored-by: Claude Sonnet 4.6 <noreply@anthropic.com>


## v0.2.3 (2026-03-06)

### Other

- 🏖️ Support more usecases ([#6](https://github.com/asaf-kali/pimp-my-repo/pull/6),
  [`c5b0d5d`](https://github.com/asaf-kali/pimp-my-repo/commit/c5b0d5df7f0dd87d89cc30246e30d244754d537e))

* Sort our subprocess.run calls

* UV boost: add more support

* Ruff boost robustness

* Mypy robustness fixes

- 🏭️ Refactoring and code style ([#4](https://github.com/asaf-kali/pimp-my-repo/pull/4),
  [`c652b06`](https://github.com/asaf-kali/pimp-my-repo/commit/c652b06beeab3883dac25ff9844835b182db4e69))

Adjust project code quality

### 🐛

- 🐛 Stability fixes ([#8](https://github.com/asaf-kali/pimp-my-repo/pull/8),
  [`7c21c42`](https://github.com/asaf-kali/pimp-my-repo/commit/7c21c4226e693ab52d1a507321f40fdd53237835))

### 📜

- 📜 Add LICENSE ([#7](https://github.com/asaf-kali/pimp-my-repo/pull/7),
  [`703d869`](https://github.com/asaf-kali/pimp-my-repo/commit/703d8690eecb4f4c6777f5cbd0c257c10f7b67d8))

### 🛠️

- 🛠️ Bug fixes and refactoring ([#5](https://github.com/asaf-kali/pimp-my-repo/pull/5),
  [`20575c7`](https://github.com/asaf-kali/pimp-my-repo/commit/20575c71a982e36761dec0065a3745909209eb93))


## v0.2.2 (2026-02-25)

### 🐛

- 🐛 Fix release job
  ([`fc82372`](https://github.com/asaf-kali/pimp-my-repo/commit/fc82372f4849090a0c15e896e990dd15897c95b7))


## v0.2.1 (2026-02-25)

### 🏗️

- 🏗️ Implement gitignore and mypy boosts ([#3](https://github.com/asaf-kali/pimp-my-repo/pull/3),
  [`629a879`](https://github.com/asaf-kali/pimp-my-repo/commit/629a879b5ce15359872251f6880ab125992acdb6))

* Implement mypy boost

* Implement gitignore boost

* Mark slow tests

* CI fixes

* Add CI release


## v0.2.0 (2026-02-25)

### Other

- Upgrade lock
  ([`ac50ef9`](https://github.com/asaf-kali/pimp-my-repo/commit/ac50ef92b0c776bad09607a4ed1ab915a709393b))

### 🐲

- 🐲 Basic project structure implementation ([#1](https://github.com/asaf-kali/pimp-my-repo/pull/1),
  [`5a9bf5f`](https://github.com/asaf-kali/pimp-my-repo/commit/5a9bf5fd2a84901515e5989917f18d14e713bc90))

### 📌

- 📌 README: add PyPI badge
  ([`f82d6a1`](https://github.com/asaf-kali/pimp-my-repo/commit/f82d6a19b3660fff421e259a9166d565fe1f9473))

### 🔥

- 🔥 Implement UV boost ([#2](https://github.com/asaf-kali/pimp-my-repo/pull/2),
  [`a2e7704`](https://github.com/asaf-kali/pimp-my-repo/commit/a2e7704a7018b6c6870d65d6a324b25f12158542))

* Lint fixes, adjsut structure

* Implement uv

* Implement repo test util

* Make use of dmypy

* Add tests

* Code quality fixes

### 🛠️

- 🛠️ Refactor justfile to use RUN variable for command execution
  ([`de8bac5`](https://github.com/asaf-kali/pimp-my-repo/commit/de8bac51cfc80161ecf284a1968a027a2ab9fb75))


## v0.1.2 (2025-12-10)

### 🏗️

- 🏗️ Add CI jobs
  ([`df82209`](https://github.com/asaf-kali/pimp-my-repo/commit/df82209977ca400760dc2ff1442470e08c4137db))

### 🛠️

- 🛠️ Add build and release commands
  ([`5a8cb36`](https://github.com/asaf-kali/pimp-my-repo/commit/5a8cb36457de25a8421e8fcc3bbafea5c633c9e5))


## v0.1.1 (2025-12-09)

### ✨

- ✨ Migrate to UV
  ([`ba15840`](https://github.com/asaf-kali/pimp-my-repo/commit/ba158400a9f7e373f2723d12cd60f796ead8bcf6))

### 📜

- 📜 Adjust README
  ([`bb8231b`](https://github.com/asaf-kali/pimp-my-repo/commit/bb8231b90df3840bc2fb12ddbf248597a22de7e2))


## v0.1.0 (2025-12-10)

### 🎉

- 🎉 Initial commit
  ([`db8d0c9`](https://github.com/asaf-kali/pimp-my-repo/commit/db8d0c9881322d6db2e309e84140f1d3e3fdf6c6))
