# pimp-my-repo project memory

## Meta
- When told to remember something, add it here unless it's clearly personal/behavioral (then use `~/.claude/`).
- When adding/changing project infra (justfile, CI workflows, major directory structure, etc.), update this file to reflect the change. Only address important tools/commands/workflows, not minor details.

## What it does
CLI tool (`pmr`) that "boosts" a target Python repo by adding tooling (ruff, mypy, uv, gitignore).
Each boost: configures the tool in `pyproject.toml`, runs it, suppresses all violations, commits.

## Dev workflow
- `just lint` — format + ruff check + pre-commit
- `just test` — pytest
- `just run-checks` — trigger CI Checks workflow on current branch and follow output; Ctrl+C exits follow.
- Always run `just lint && just test` before committing.

## Architecture
- `pimp_my_repo/core/boosts/` — one file per boost, each subclasses `Boost`
- `Boost.apply()` — called by booster; must be idempotent
- `Boost.commit_message()` — message for the final suppression commit
- `pimp_my_repo/core/booster.py` — orchestrates boosts, handles git revert on failure
- `pimp_my_repo/core/tools/` — shared tools: `uv`, `git`, `pyproject`

## Ruff boost (`ruff.py`)
- Writes `[tool.ruff.lint] select = ["ALL"]` + ignore list to pyproject.toml
- Iterates: run `ruff check --output-format=json` → add `# noqa: CODE` → run `ruff format`
- Syntax error files (JSON `"code": "invalid-syntax"`) → added to `[tool.ruff] extend-exclude`
- `_UNSUPPRESSIBLE_CODES = {"ERA001"}` — added to ignore list instead of noqa

## Mypy boost (`mypy.py`)
- Writes `[tool.mypy] strict = true` to pyproject.toml
- Iterates: run `mypy .` → add `# type: ignore[code]` → run ruff suppress if ruff is configured
- **Syntax errors** (`[syntax]` code) → excluded via `[tool.mypy] exclude` (regex, `re.escape(path)`); non-syntax violations from the same file are still suppressed inline
- **"Source file found twice"** → exclude PARENT DIRECTORY (with `/`) not the file itself — mypy's exclude can't prevent discovery-stage errors for specific files
- **"errors prevented further checking"** → parse uncoded errors (no `[code]`), exclude those files
- **Note**: mypy `exclude` only prevents file discovery, not import following. If another file imports an excluded module, mypy still checks it
- **Triple-quoted strings** (critical): if violation line opens `"""` or `'''`, placing comment after it embeds it inside the string. Fix:
  - `func("""` → split at `"""`, comment after `(`, triple-quote to next line
  - `x = """` → place `# type: ignore` on the **closing** `"""` line (mypy recognizes it there); do NOT wrap with `()` — ruff UP034 removes extraneous parens, causing oscillation
  - Process violations in **reverse line order** so line insertions don't shift pending indices
- **`'"""'` (single-quoted string containing triple double-quotes)**: must NOT be treated as an unclosed triple-quote; `_find_unclosed_triple_quote_pos` skips single-char quoted strings before checking for triple-quote sequences
- **Parsing**: single-pass over normalized output; each line falls into exactly one category (coded error, note, uncoded error, invalid pkg name, summary, or unhandled)
- **`show_error_end = true`**: mypy outputs `path:line:col:endline:endcol: error:` — all regexes use `(?::\d+)*` (not `(?::\d+)?`) to handle arbitrary extra colon-number segments

## Key implementation details
- TOML: `re.escape("a/b.py")` = `a/b\.py` → serialized as `a/b\\.py` in file (double backslash)
- Mypy `exclude` = regex patterns; ruff `extend-exclude` = glob patterns
- `_MAX_MYPY_ITERATIONS = 10`, `_MAX_RUFF_ITERATIONS = 7`
- `unused-ignore` violations use `!code` prefix in internal representation to REMOVE codes

## Testing conventions
- All mocks in fixtures using `patch.object`, never inside test functions
- Test only through public interfaces; patching private functions is allowed
- Fixtures: `mock_repo`, `boost_tools`, `ok_result`, `fail_result` in `conftest.py`
- `patched_mypy_apply` / `patched_ruff_apply` fixtures mock subprocess + git
