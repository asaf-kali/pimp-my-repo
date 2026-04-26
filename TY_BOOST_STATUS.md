# TyBoost — Work-in-Progress Status

**Branch:** `ty-fixes`
**Last updated:** 2026-04-25
**Tests:** 424 passed, lint clean

---

## What Was Done

### Phase 1 — Core TyBoost (merged to main as 0.5.0)
- `pimp_my_repo/core/boosts/ty.py` — full `TyBoost` implementation
- `pimp_my_repo/core/registry.py` — `TyBoost` added to `_OPT_IN_BOOSTS`
- `pimp_my_repo/cli/main.py` — `--ty` flag added (replaces mypy with ty in boost list)
- `tests/test_ty_boost.py` — unit tests
- `tests/test_cli.py` — CLI tests for `--ty` flag and `_resolve_boosts()` paths

### Phase 2 — Bug fixes on `ty-fixes` branch (commit `59a9fa7`)
All in `pimp_my_repo/core/boosts/ty.py`:

1. **Space escaping for ty glob patterns** (`_escape_ty_glob`)
   ty's `[tool.ty.src] exclude` globs don't support literal spaces.
   Fix: `_escape_ty_glob(path)` replaces ` ` → `\ ` before adding to excludes.
   Triggered by: cavity-design repo has notebook files with spaces in names.

2. **Suppress unused-ignore-comment oscillation at config level**
   Added `[tool.ty.rules] unused-ignore-comment = "ignore"` and
   `unused-type-ignore-comment = "ignore"` in `_ensure_ty_config`.
   Root cause: ty 0.0.x inconsistently reports `unresolved-attribute` on a line,
   PMR adds `# ty: ignore`, then ty reports `unused-ignore-comment` for the same
   ignore → PMR removes it → ty reports the error again → infinite loop.
   The `unused-type-ignore-comment` variant prevents ty from flagging mypy's
   `# type: ignore` comments that are valid for mypy but unknown to ty.

3. **`invalid-syntax` files → exclude, don't inline-suppress**
   In `_suppress_violations_iteration`, files with `invalid-syntax` violations
   are extracted and passed to `_add_ty_excludes` before inline suppress runs.
   Root cause: files with Python syntax errors can't be parsed, so a
   `# ty: ignore[invalid-syntax]` comment is never seen — exclusion is the only option.

4. **Triple-quote handling for function call case**
   Added `_find_unclosed_triple_quote_pos` (adapted from `mypy.py`) and
   `_place_ty_ignore` to replace the direct `_merge_ty_ignore` call in
   `_apply_ty_ignores_to_file`.
   When a violation is on a line that opens an unclosed triple-quoted string via a
   function call (`func("""`), the comment is placed after `(` and `"""` is moved
   to the next line — so the comment is real Python, not embedded string content.
   Example fixed: `test_github_links.py:34`
   `github_links.CodeLocator.from_code("""` → comment lands outside the string.

5. **No-progress detection → file exclusion fallback**
   `_apply_ty_ignores` now returns `bool` (True if any file was modified).
   `_apply_ty_ignores_to_file` compares before/after content and returns `bool`.
   `_suppress_violations_iteration`: if `_apply_ty_ignores` returns False (no-op),
   the affected files are excluded via `_add_ty_excludes`.
   This handles violations inside strings (e.g. f-string content lines) where no
   placement strategy works.

6. **Reverse sort order in `_apply_ty_ignores_to_file`**
   Processes lines in descending order so that line insertions (triple-quote fix)
   don't shift the indices of later violations in the same file.

---

## E2E Test Status

### cavity-design — ✅ FIXED (space escaping)
Was failing because ty couldn't exclude notebook files with spaces in names.

### scikit-learn — ⚠️ NOT YET VERIFIED with new code
The repos at `/tmp/pmr/scikit-learn` and `/tmp/pmr/django` still contain the
**partially-modified state from the previous session** (some `# ty: ignore` were
added by the old code, but no `[tool.ty]` config was ever written to pyproject.toml).
These repos have NOT been reset and re-run with the new code.

**Remaining violations before the new code was applied:**
```
sklearn/externals/array_api_compat/_internal.py:44:38: error[unresolved-attribute]
sklearn/externals/array_api_compat/common/_helpers.py:787:22: warning[unused-type-ignore-comment]
sklearn/externals/array_api_compat/common/_helpers.py:787:57: warning[unused-ignore-comment]
```

- `_helpers.py:787` → fixed by fix #2 (unused-ignore config rule)
- `_internal.py:44` → this is `{f.__name__}` inside an f-string opened with `f"""\`
  on the previous line. The violation line itself has no triple-quote opener, so
  `_find_unclosed_triple_quote_pos` returns None and `_merge_ty_ignore` runs normally.
  The comment ends up on line 44 which IS inside the string (string content, not Python).
  This is NOT fixed by the triple-quote function-call path (that handles `func("""`).
  Fix #5 (no-progress detection) should catch this: after one iteration where the
  comment is added (content changes), the second iteration adds the same comment again
  (no change) → no-op → `_internal.py` gets excluded.

### django — ⚠️ NOT YET VERIFIED with new code
**Remaining violations before the new code was applied:**
```
django/contrib/gis/geos/mutable_list.py:65:68: warning[unused-ignore-comment]
django/contrib/gis/geos/mutable_list.py:69:80: warning[unused-ignore-comment]
tests/sphinx/test_github_links.py:34:19: error[unresolved-attribute]
tests/test_runner_apps/tagged/tests_syntax_error.py:11:2: error[invalid-syntax]
```

- `mutable_list.py:65/69` → fixed by fix #2 (unused-ignore config rule)
- `test_github_links.py:34` → `github_links.CodeLocator.from_code("""` — fixed by fix #4
  (triple-quote function call detection)
- `tests_syntax_error.py:11` → fixed by fix #3 (invalid-syntax → exclude)

---

## What Still Needs To Be Done

### 1. Reset and re-run e2e tests
The repos at `/tmp/pmr/scikit-learn` and `/tmp/pmr/django` need to be reset to
their original state (before any PMR runs) and `just test-e2e` re-run with the
`--ty` flag:

```bash
just test-e2e https://github.com/scikit-learn/scikit-learn.git <commit-sha> --ty
just test-e2e https://github.com/django/django.git <commit-sha> --ty
```

Or use the commit SHAs from `.github/workflows/checks.yml`.

### 2. Investigate scikit-learn `_internal.py:44` more carefully
The f-string assignment case (`wrapped_f.__doc__ = f"""\` on line 43, violation
reported at line 44 which is string content) may behave as follows with the new code:

- **Iteration 1:** `_merge_ty_ignore` adds `# ty: ignore[unresolved-attribute]` to
  line 44 (string content). File changes. Returns True.
- **Iteration 2:** Same violation reported. `_merge_ty_ignore` is a no-op (comment
  already there). File unchanged. `_apply_ty_ignores` returns False.
  No-progress branch: `_internal.py` is excluded. Returns True.
- **Iteration 3:** ty runs without `_internal.py`. Should pass (or fewer violations).

**The question:** Does this actually work end-to-end? The no-progress detection relies
on the exact same violation being reported for the same file in consecutive iterations.
If ty also starts reporting a NEW violation on the same file in iteration 2 (that wasn't
there in iteration 1), the "changed" flag could be True (due to the new violation line),
and the no-progress detection for line 44 wouldn't trigger. Needs empirical testing.

### 3. Investigate test_github_links.py transformation correctness
The triple-quote fix for `test_github_links.py:34` modifies the string content passed
to `CodeLocator.from_code()`. Before: `"""  # ty: ignore[...]\nfrom a import b, c\n...`.
After: `"""\nfrom a import b, c\n...`.

The test parses this Python code to extract function/class names. The first "line" of the
string changed. Verify the test still passes after the fix is applied.

### 4. Verify the `_run_ty_check` TYPE_CHECKING guard
In the current code, `_run_ty_check` has return type `CommandResult` (via TYPE_CHECKING
import). The `"CommandResult"` string annotation was removed in the new code. Lint passes,
but double-check this doesn't cause runtime issues.

### 5. Consider: assignment triple-quote case
For `f"""\` (backslash continuation inside f-string), there's no perfect inline fix.
The fallback exclusion handles it, but it means those lines are skipped permanently.
An alternative: detect when a violation line is CONTENT of a multi-line string (scan
backward for an unclosed triple-quote), then try putting the ignore on the opening line.
This is complex and may not be necessary if the fallback exclusion works acceptably.

### 6. Commit and push
Once e2e tests pass:
```bash
git add -u
git commit -m "..."
git push origin ty-fixes
```
Then open a PR into main.

---

## Key File Locations

| File | Purpose |
|------|---------|
| `pimp_my_repo/core/boosts/ty.py` | Main implementation |
| `tests/test_ty_boost.py` | Unit tests |
| `tests/test_cli.py` | CLI flag tests |
| `.github/workflows/checks.yml` | E2E matrix (includes `--ty` for pandas) |
| `/tmp/pmr/scikit-learn/` | Partially-modified scikit-learn (needs reset) |
| `/tmp/pmr/django/` | Partially-modified django (needs reset) |

---

## Key Implementation Notes

### Why no-progress detection works for `_internal.py`
1. Iteration 1: adds `# ty: ignore` inside the f-string → file changes → returns True
2. Iteration 2: same ignore already there → `_merge_ty_ignore` no-op → file unchanged
   → `_apply_ty_ignores` returns False → no-op branch excludes the file → returns True
3. Iteration 3: ty runs with file excluded → violation gone

### Why the triple-quote function-call fix works for `test_github_links.py:34`
Original: `github_links.CodeLocator.from_code("""` (opens unclosed `"""`)
`_find_unclosed_triple_quote_pos` → returns `TripleQuotePos(position=..., quote='"""')`
`code_part = "...from_code("` ends with `(` → function-call branch
New line 34: `...from_code(  # ty: ignore[unresolved-attribute]`
Inserted line 35: `    """`
ty sees the `# ty: ignore` on line 34 (outside the string) → suppresses the error.

### Why unused-ignore-comment config beats inline handling
Setting `unused-ignore-comment = "ignore"` in `[tool.ty.rules]` means ty never reports
it. This is simpler than the `_UNUSED_IGNORE_CODE` handling in `_merge_ty_ignore`, which
tries to remove ignore comments — causing oscillation when the underlying error returns.
The `_UNUSED_IGNORE_CODE` handling in `_merge_ty_ignore` is kept for completeness (and
has unit tests), but is never triggered in practice with the config-level suppression.
