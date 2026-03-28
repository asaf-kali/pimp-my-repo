# CHANGELOG


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
