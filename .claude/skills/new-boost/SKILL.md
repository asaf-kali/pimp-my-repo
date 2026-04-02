---
name: new-boost
description: >
  Implement a new boost in pimp-my-repo. Use this skill whenever the user asks
  to add, create, or implement a new boost, a new tool integration, or a new
  automated enhancement step for PMR. Trigger on any mention of "new boost",
  "add a boost", "create a boost", or "implement X boost".
---

# new-boost

A boost configures a tool in a target repo: writes config, runs the tool,
suppresses violations, and commits. Adding one correctly requires thinking
through idempotency, skip conditions, tests, and e2e validation up front.

## Inputs

Before writing any code, clarify:

- **What tool** does this boost configure or install?
- **What files** does it write or modify?
- **Idempotency marker** — what condition proves "already applied"? (e.g., a
  config section in pyproject.toml, a header in a file)
- **Skip conditions** — when should the boost raise `BoostSkippedError` without
  touching anything? (tool unavailable, preconditions absent, already applied)
- **Default or opt-in** — should it run by default or require `--only`?
- **Commit message** — emoji + short verb phrase (follow existing style)

Nail these before opening a file. Idempotency in particular is architectural,
not an afterthought.

## Workflow

### Step 1 — Implement the boost

Create `pimp_my_repo/core/boosts/<name>.py`. Follow the project's file
structure order (logger → types → constants → classes → public fns → private
fns). Subclass `Boost`:

```python
class <Name>Boost(Boost):
    def apply(self) -> None:
        # 1. Check idempotency / preconditions — raise BoostSkippedError BEFORE touching anything
        # 2. Make changes (write files, run tools)

    def commit_message(self) -> str:
        return "<emoji> <short description>"
```

**Key rules for `apply()`:**
- Guard with `BoostSkippedError` at the top, before any mutations. The contract
  is strict: if you're going to skip, you have not yet changed anything.
- Use `self.git.write_file(relative_path, content)` to write files — it keeps
  git tracking correct.
- Use `self.pyproject` for `pyproject.toml` reads/writes (tomlkit-based,
  preserves formatting).
- Use `self.http.request(url)` for HTTP fetches.
- Use `self.uv.exec(*args)` for uv subprocesses.

**Register it** in `pimp_my_repo/core/registry.py` — append to `_DEFAULT_BOOSTS`
or `_OPT_IN_BOOSTS` depending on your Step 0 decision.

Run lint immediately after:

```bash
just lint
```

Fix all issues before proceeding.

### Step 2 — Write unit tests

Create `tests/test_<name>_boost.py`. Follow the pattern from existing tests:

1. **Boost fixture** — a `@pytest.fixture` that instantiates the boost with
   `boost_tools`:
   ```python
   @pytest.fixture
   def <name>_boost(boost_tools: BoostTools) -> <Name>Boost:
       return <Name>Boost(boost_tools)
   ```

2. **Patched fixture** — if the boost calls subprocess or HTTP, patch those at
   the module level using `mock.patch.object`. Create a `@dataclass` to bundle
   the boost + mocks, yield it from a `@pytest.fixture`. Never patch inside
   test functions.

3. **Test cases to cover:**
   - Happy path: boost applies, files are created/modified correctly
   - Idempotency: calling `apply()` on an already-boosted repo raises
     `BoostSkippedError` (or produces no-op). Test this by running `apply()`
     twice on `mock_repo` and asserting the second call skips.
   - Each distinct skip condition (tool absent, precondition missing, etc.)
   - `commit_message()` returns the expected string
   - `get_name()` returns the expected name

4. **Testing conventions:**
   - All patches in reusable fixtures via `patch.object`, never inline
   - Test only through public interface (`apply()`, `commit_message()`)
   - Patching private functions (`_foo`) is fine
   - Use `mock_repo.write_file(path, content)` to set up fixture repo state

Run after writing tests:

```bash
just lint && just test
```

### Step 3 — Create a local e2e fixture

Create `tests/fixtures/<boost-name>/` — the smallest possible repo that causes
the boost to have meaningful work to do. Include only what is necessary:

- A `pyproject.toml` (usually needed; content depends on the boost)
- A few `.py` files if the boost touches Python source
- Any other config files the boost needs to detect

Register the fixture in `tests/test_e2e_local.py` by adding its name to
`_FIXTURES`:

```python
_FIXTURES = [
    "minimal-package",
    "setup-cfg-package",
    "<boost-name>",     # ← add here
]
```

Then run it:

```bash
just test-e2e-local <boost-name>
```

The e2e test verifies:
- PMR runs to completion on the fixture
- No uncommitted files remain in the repo afterward
- Ruff passes (format + check) on the result
- Mypy passes on the result (if mypy is configured)

**If the fixture fails**, diagnose by reading the PMR log output. Fix PMR code,
re-run `just lint && just test`, then re-run the fixture. Repeat until the
fixture passes cleanly.

### Step 4 — Verify no regressions in the full suite

```bash
just lint && just test
```

This runs all unit tests including the local e2e matrix (`minimal-package`,
`setup-cfg-package`, and your new fixture). If any existing test breaks, fix it
before proceeding — your boost may have an ordering interaction or side effect
on other boost behavior.

### Step 5 — Validate idempotency end-to-end (for non-trivial boosts)

If the boost makes changes that could accumulate on repeated runs (appending
to files, adding config sections), validate end-to-end idempotency:

1. Run PMR on the local fixture: `just test-e2e-local <boost-name>`
2. Run PMR again on the same repo path (the fixture is already boosted)
3. Verify the second run either skips cleanly or produces no new commits

This catches cases where the unit-level idempotency check passes but the
real tool output triggers a different code path.

### Step 6 — Spot-check on a real remote repo (optional)

For boosts that interact with the broader Python ecosystem, pick a
representative repo from the CI matrix in `.github/workflows/checks.yml` and
confirm it still passes:

```bash
just test-e2e <repo-url> <sha>
```

Remote e2e is slow — use it as a final sanity check, not as the iteration loop.
If a remote repo fails, follow the support-repo skill workflow (create a
fixture that reproduces the failure, fix, re-test).

---

## Idempotency patterns (reference)

| Situation | Pattern |
|-----------|---------|
| Boost writes a config section to pyproject.toml | Check for the section at the top of `apply()`, raise `BoostSkippedError` if present |
| Boost appends to an existing file | Add a unique header/marker; check for it before appending |
| Boost conditionally adds recipes/entries | Collect what's missing; if nothing is missing, raise `BoostSkippedError` |
| Boost invokes a tool iteratively | Cap iterations with `_MAX_<TOOL>_ITERATIONS`; stop when no new violations found |

## Common failure modes

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Second `apply()` call doesn't raise `BoostSkippedError` | Idempotency check too narrow | Broaden the check or use a unique marker |
| e2e fixture leaves uncommitted files | `apply()` writes a file without staging it | Use `self.git.write_file()` + ensure git tracks it |
| Tool runs infinitely | Suppression introduces new violations | Add oscillation-prevention codes to ignore list |
| Boost applies to repos where it shouldn't | Skip condition too permissive | Tighten the precondition check |
| `just lint` fails after implementation | File structure order wrong, type hints missing | Follow CLAUDE.md file structure order |

## Important constraints

- **`BoostSkippedError` before any changes**: if `apply()` is going to skip,
  it must do so before writing a single byte. The orchestrator reverts git
  state on non-skip exceptions, but relies on this contract for skips.
- **No partial application**: either the full boost applies, or nothing does.
  If a multi-step boost might fail halfway, consider intermediate commits so
  the revert is meaningful.
- **Run `just lint && just test` after every code change** before running e2e.
- **Read source before editing**: understand the code flow, not just the error.
