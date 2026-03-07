# CHANGELOG


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
