# Pimp My Repo

🧙🏼‍♂️ A CLI wizard designed to modernize your Python repositories by adding essential development tools.

[![PyPI](https://img.shields.io/pypi/v/pimp-my-repo)](https://pypi.org/project/pimp-my-repo/)
[![Checks](https://github.com/asaf-kali/pimp-my-repo/actions/workflows/checks.yml/badge.svg)](https://github.com/asaf-kali/pimp-my-repo/actions/workflows/checks.yml)
[![Tests](https://github.com/asaf-kali/pimp-my-repo/actions/workflows/tests.yml/badge.svg)](https://github.com/asaf-kali/pimp-my-repo/actions/workflows/tests.yml)
[![Release](https://github.com/asaf-kali/pimp-my-repo/actions/workflows/release.yml/badge.svg)](https://github.com/asaf-kali/pimp-my-repo/actions/workflows/release.yml)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Type checked: mypy](https://img.shields.io/badge/type%20check-mypy-22aa11)](http://mypy-lang.org/)

## Features

**pimp-my-repo** will help you:
- 🚀 Integrate [uv](https://docs.astral.sh/uv/) for modern dependency management.
- ✨ Configure [ruff](https://github.com/astral-sh/ruff) to keep your code clean and consistent.
- 🐍 Integrate [mypy](https://github.com/python/mypy) for static type checking to catch potential bugs early.
- 🏖️ Set up [pre-commit](https://pre-commit.com/) hooks to ensure code quality before changes are committed.
- 🎢 Generate a [justfile](https://github.com/casey/just) with common commands like `install`, `test` and `lint`.
- 🏗️ Add CI job configurations for `GitHub Actions` or `GitLab Pipeline` to enforce your rules in a continuous integration
  environment.

## Why?

Adopting strict linting and type checking in a legacy Python repo is painful — there are hundreds
of existing violations to deal with before you can even turn the rules on.
**pimp-my-repo** automates that process: it configures common linting tools in strict mode, automatically
suppresses all existing violations (via `# noqa` / `# type: ignore` comments), and commits the
result. The goal is a clean baseline instantly — after which new code must comply.
Once merged, you can gradually revisit and fix the suppressed issues at your own pace.

## Usage

In your repository root, run:
```bash
uvx pimp-my-repo
```

Alternatively, install `pimp-my-repo` globally and use it in any repository:

```bash
# With UV:
uv tool install pimp-my-repo

# With pipx:
pipx install pimp-my-repo
```


## License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details
