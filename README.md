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

## Why legacy repos stay legacy

Adopting strict linting and type checking sounds great — until you run Ruff or Mypy for the first time and see 17,000 violations. Fixing them all before you can enforce a single rule isn't practical, so the tools stay off or "loose," and the debt compounds.

## The baseline approach

`pimp-my-repo` skips the manual fix step entirely:

1. **Configures tools in strict mode**: Ruff with all rules enabled, Mypy with `--strict`.
2. **Suppresses all existing violations**: automatically adds `# noqa` and `# type: ignore` to every current offender.
3. **Commits the result**: you get a clean, passing CI baseline immediately.

New code must comply from day one. Legacy violations are silenced but visible; fix them incrementally, at your own pace, without blocking anyone.

## What gets added

- 🚀 **[uv](https://docs.astral.sh/uv/)** — modern dependency management
- ✨ **[Ruff](https://github.com/astral-sh/ruff)** — linting and formatting, strict mode, all existing violations suppressed
- 🐍 **[Mypy](https://github.com/python/mypy)** — static type checking, strict mode, all existing errors suppressed
- 🏖️ **[pre-commit](https://pre-commit.com/)** — hooks to enforce quality before every commit
- 🎢 **[just](https://github.com/casey/just)** — task runner with `install`, `test`, and `lint` recipes out of the box
- 🏗️ **CI** _(coming soon)_ — GitHub Actions or GitLab Pipeline configuration

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
