# Pimp My Repo

[![PyPI](https://img.shields.io/pypi/v/pimp-my-repo)](https://pypi.org/project/pimp-my-repo/)
[![CI](https://github.com/asaf-kali/pimp-my-repo/actions/workflows/ci.yml/badge.svg)](https://github.com/asaf-kali/pimp-my-repo/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/asaf-kali/pimp-my-repo/graph/badge.svg)](https://codecov.io/gh/asaf-kali/pimp-my-repo)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Type checked: mypy](https://img.shields.io/badge/type%20check-mypy-22aa11)](http://mypy-lang.org/)

🧙🏼‍♂️ **One command to modernize them all**.

Strict linting, type checking, and CI for your legacy Python repo, with near-zero manual work. Run it once in your repo root — it creates its own local branch (nothing is pushed), so you can always walk away:

```bash
uvx pimp-my-repo
```

Alternatively, hand it off to your LLM — it can run PMR, review the result with full knowledge of the codebase, and clean up anything the automated run got slightly wrong:

<details>
<summary>📋 LLM prompt (click to expand)</summary>

```
From the repo root, on a clean branch, run `uvx pimp-my-repo`.

When the run finishes, read the output and follow any instructions printed.
Since you know this repo's structure, conventions, and goals, review the
created branch and fix anything that looks wrong or misconfigured — CI jobs,
pre-commit hooks, justfile recipes, etc.

If the run failed:
  1. Find and inspect the log file it mentions.
  2. If the failure has a straightforward fix in the repo's own code
     (e.g. a broken import, a missing config key, an incompatible
     dependency), go back to the original branch, delete the PMR branch,
     apply the minimal fix on a new branch, then re-run `uvx pimp-my-repo`
     from there.
  3. If the failure looks like a PMR bug or something you can't easily fix,
     stop and report what you found.

For context and reference on PMR, see https://github.com/asaf-kali/pimp-my-repo/blob/main/README.md.
```

</details>

## Why legacy repos stay legacy

Adopting strict linting and type checking sounds great — until you run Ruff or Mypy for the first time and see 17,000 violations. Fixing them all before you can enforce a single rule isn't practical, so the tools stay off or "loose," and the debt compounds.

## The baseline approach

`pimp-my-repo` skips the manual fix step entirely:

1. **Configures tools in strict mode**: Ruff with all rules enabled, Mypy with `--strict` (or ty with `error-on-warning`).
2. **Suppresses all existing violations**: automatically adds `# noqa` and `# type: ignore` / `# ty: ignore` to every current offender.
3. **Commits the result**: you get a clean, passing CI baseline immediately.

New code must comply from day one. Legacy violations are silenced but visible; fix them incrementally, at your own pace, without blocking anyone.

## What gets added

- 🚀 **[uv](https://docs.astral.sh/uv/)** — modern dependency management
- ✨ **[Ruff](https://github.com/astral-sh/ruff)** — linting and formatting, strict mode, all existing violations suppressed
- 🐍 **[Mypy](https://github.com/python/mypy)** — static type checking, strict mode, all existing errors suppressed
- ⚡ **[ty](https://docs.astral.sh/ty/)** _(opt-in via `--ty`)_ — Astral's fast type checker as a drop-in alternative to mypy
- 🏖️ **[pre-commit](https://pre-commit.com/)** — hooks to enforce quality before every commit
- 🎢 **[just](https://github.com/casey/just)** — task runner with `install`, `test`, and `lint` recipes out of the box
- 🏗️ **CI** _(coming soon)_ — GitHub Actions or GitLab Pipeline configuration

## Using ty instead of mypy

Pass `--ty` to replace the mypy boost with ty:

```bash
uvx pimp-my-repo --ty
```

ty runs dramatically faster than mypy and catches a different (often broader) set of type errors.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
