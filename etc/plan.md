# Pimp My Repo - Implementation Plan

## Technologies
- **rich** for UX (progress bars, tables, formatted output)
- **typer** for CLI (command structure, argument parsing)
- **loguru** for logging (structured logging, different log levels)

## General Flow

### Alpha Version (Non-Interactive)
- All decisions made automatically, no prompts (except `--path` which defaults to pwd)
- Design must support future interactive wizard mode
- CLI flag: `--wizard` (default: false) - enables interactive mode in future

### Pre-Flight Checks
- Verify git state is clean (fail if not)
- Create and switch to new `pmr` branch
- Detect existing dependency files (`requirements.txt`, `setup.py`, `pyproject.toml`, etc.)

### State Management
- Working directory: `~/.local/share/pimp-my-repo/` (or similar)
- Per-project JSON state file keyed by git origin URL
- Store all user inputs/decisions in state file
- Log all changes in state file
- Allows re-running tool from clean state without re-prompting

### Boost Architecture
- Each tool integration is a **boost** (modular, extensible design)
- Boost interface:
  - Pre-conditions check
  - Migration/application
  - Verification (run tool, ensure it works)
- Boosts run independently and sequentially
- After each boost: commit changes to `pmr` branch
- Verify project validity after each boost (use existing project tests if available)

## Supported Boosts (Alpha)

### 1. uv Boost
- Create `pyproject.toml` if it doesn't exist
- Migrate `requirements.txt` to uv format (if exists)
- Do NOT add `uv.lock` to `.gitignore`

### 2. ruff Boost
- Enable all rules (`select = ["ALL"]`)
- Line length: 120
- Configure both formatting and linting
- Migration strategy:
  - Run safe formatting and linting
  - For each existing error, add `# noqa: <ERROR_ID>` comment on the line

### 3. mypy Boost
- Strict mode: enable all features and checks
- Configure in `pyproject.toml` (not `mypy.ini`)
- Add type stubs for common dependencies

### 4. pre-commit Boost
- Use hooks from this project as reference (see `.pre-commit-config.yaml`)
- Create config file + install hooks immediately

### 5. justfile Boost
- Use this project's justfile as reference
- Commands: install, test, lint, format, type-check, etc.
- Detect existing `Makefile` (for future migration, not in alpha)

### 6. CI/CD Boost
- **Not included in alpha**

## Implementation Structure

```
pimp_my_repo/
├── cli/
│   ├── __init__.py
│   ├── main.py              # Entry point, typer app
│   └── commands/
├── core/
│   ├── __init__.py
│   ├── git.py              # Git operations (check clean, branch, commit)
│   ├── state.py            # State management (read/write JSON)
│   ├── detector.py         # Detect existing configs/tools
│   └── boost/
│       ├── __init__.py
│       ├── base.py         # Boost base class/interface
│       ├── uv.py
│       ├── ruff.py
│       ├── mypy.py
│       ├── pre_commit.py
│       └── justfile.py
├── templates/              # Jinja2 templates for configs
│   ├── pyproject.toml.j2
│   ├── ruff.toml.j2
│   ├── pre-commit.yaml.j2
│   └── justfile.j2
└── models/
    ├── __init__.py
    └── state.py            # Pydantic models for state
```

## Boost Interface

Each boost must implement:
- `check_preconditions()` - Verify prerequisites (e.g., git clean, files exist)
- `apply()` - Perform the migration/configuration
- `verify()` - Run the tool and ensure it works correctly
- `commit_message()` - Generate commit message for this boost

## Future Considerations (Not Alpha)
- Interactive wizard mode
- Command-line flags for selective boosts
- Dry-run mode
- Config file support (`.pimp-my-repo.toml`)
- Presets (minimal, strict, relaxed)
- CI/CD integration
- Makefile migration
- Rollback support (rely on git for alpha)
