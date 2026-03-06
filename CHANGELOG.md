# CHANGELOG


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
