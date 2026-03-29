---
name: support-repo
description: >
  Add a new repository to pimp-my-repo's e2e test suite and CI pipeline.
  Use this skill whenever the user asks to add a repo, test a repo with PMR,
  onboard a new repo to CI, or check if PMR supports a given project URL.
  The skill runs the e2e test locally, fixes any PMR code issues found, then
  adds the repo to CI once it passes. Trigger on any mention of adding/testing
  a repo URL against PMR.
---

# support-repo

Given a target repo URL, iteratively get PMR's e2e test passing for it, then
add it to CI. Only PMR code in this repo may be changed — never patch the
target repo itself.

## Inputs

- **repo**: GitHub URL (e.g. `https://github.com/org/name`)
- **rev** (optional): specific commit SHA to test against; if omitted, resolve HEAD automatically

## Workflow

### Step 0 — Resolve target SHA

```bash
git ls-remote <repo> HEAD | awk '{print $1}'
```

Save this as `<sha>`. All subsequent commands use `--rev <sha>` so the test is
reproducible. If the user already provided a SHA, use that.

### Step 1 — Run local e2e test

```bash
just test-e2e <repo> --rev <sha>
```

Capture full output. Proceed based on result:

- **Passes** → go to [Step 3 (Add to CI)](#step-3--add-to-ci)
- **Fails** → go to [Step 2 (Fix loop)](#step-2--fix-loop)

### Step 2 — Fix loop (max 5 iterations)

#### 2a. Diagnose

Read the failure output carefully. Common failure categories and where to look:

| Symptom | Likely cause | Where to fix |
|---|---|---|
| `uv lock` fails with Python version | `migrate-to-uv` running its own lock | `uv.py` — `--skip-lock` flag |
| `uv add -r <file>` — file not found | `migrate-to-uv` already migrated + deleted the file | `uv.py` — guard with `file_path.exists()` |
| mypy / ruff in infinite loop | Oscillating suppression logic | relevant boost file |
| Unexpected tool crash | Exception in boost code | trace the stack |

Read the relevant source files before editing. Understand the code flow, not just the error message.

#### 2b. Fix

Apply the minimal fix to PMR code (anything under this repo: source, tests, config).
After any code change, run:

```bash
just lint && just test
```

Fix any lint/test failures before proceeding.

#### 2c. Retry

```bash
just test-e2e <repo> --rev <sha>
```

- **Passes** → go to Step 3
- **Fails again** → increment iteration counter, return to 2a
- **5 iterations exhausted without passing** → stop, report what was attempted and what still fails, ask the user how to proceed

### Step 3 — Add to CI

Edit `.github/workflows/checks.yml`. Find the `test-e2e` job matrix (it uses
`include:` objects). Add a new entry:

```yaml
- repo: <repo>.git   # ensure it ends in .git
  rev: <sha>
```

Keep entries in their current order (append at the end).

Then commit, push, and trigger CI:

```bash
git add .github/workflows/checks.yml
git commit -m "✅ Add <repo-name> to e2e tests"
git push
gh workflow run checks.yml --ref $(git branch --show-current)
```

Wait a moment, then get the run ID:

```bash
gh run list --workflow=checks.yml --limit=1 --json databaseId -q '.[0].databaseId'
```

### Step 4 — Wait for CI

Poll with:

```bash
gh run view <run-id> --json status,conclusion
```

- **Passes** → done, report success
- **Fails** → fetch the failed job logs:
  ```bash
  gh run view <run-id> --log-failed
  ```
  Diagnose, fix PMR code (counts toward the 5-iteration limit shared with local fixes), push again (no new CI trigger needed — the push re-runs the checks automatically if a PR is open, otherwise re-trigger manually), return to Step 4

## Important constraints

- **Never modify the target repo.** All fixes go into this PMR repo only.
- **Always use `--rev`** so tests are pinned to a known SHA.
- **Run `just lint && just test` after every code change** before retrying e2e.
- **5 total fix iterations** (local + CI combined). If not converging, surface the remaining failure and ask the user.
- When diagnosing, read the actual source code — don't guess from memory or assume a previous fix applies.
