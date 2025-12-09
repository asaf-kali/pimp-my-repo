# Pimp My Repo

🧙🏼‍♂️ A CLI wizard designed to modernize your Python repositories by adding essential development tools.

## Features

**pimp-my-repo** will help you:
- 🐍 Integrate [uv](https://docs.astral.sh/uv/) for modern dependency management.
- 🧹 Configure [ruff](https://github.com/astral-sh/ruff) to keep your code clean and consistent.
- 🐛 Integrate [mypy](https://github.com/python/mypy) for static type checking to catch potential bugs early.
- 🎢 Set up [pre-commit](https://pre-commit.com/) hooks to ensure code quality before changes are committed.
- 🏖️ Generate a [justfile](https://github.com/casey/just) with common commands like `install`, `test` and `lint`.
- 🏗️ Add CI job configurations for `GitHub Actions` or `GitLab Pipeline` to enforce your rules in a continuous integration
  environment.

## Installation

Install **pimp-my-repo** globally with:

```bash
# With UV:
uv tool install pimp-my-repo

# With pipx:
pipx install pimp-my-repo
```
