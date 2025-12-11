# Pimp My Repo - Implementation Plan

## Technologies
- **rich** for UX (progress bars, tables, formatted output)
- **typer** for CLI (command structure, argument parsing)
- **loguru** for logging (structured logging, different log levels)

## General Flow

For alpha, we will only implement the default flow - all desicions will be made automatically, without prompting for quesitons.
The design should take into account that in the near future, the interactive wizard could take different flows considering user input.

# Some more feature

- before starting, make sure git state is clean. fail otherwise. work on a new `pmr` branch.
- keep a questioneer answers in a state - give the tool a separate working directory (~/.local or something like this), keep a per-project json file with all the user inputs. the key will be the git origin of the project. this will allow running the tool again from the start on a clean state without asking for input again.
- each tool integration will be called a **boost**. build the project such that `boost`s can be easly added in the future. we need to decide what is the boost interface, maybe: pre-conditions check, migration, verification. Each boost will run indipendantly of the others, we will start one only after everything before it finished. after a boost is applied, commit the changes.
- consider strategies of how to verify after each boost the project is still valid - how to use existing project tests.

### Questions about the flow:

1. **Interaction Mode:**
   - Should this be an **interactive wizard** (step-by-step prompts asking what to add)? yes
   - Or a **command-line flags approach** (e.g., `pimp-my-repo --uv --ruff --mypy`)? to be supproted in the future
   - Or a **hybrid** (default interactive, but flags to skip prompts)? for alpha, support only --wizard: enable interactive mode. this flag is false by default - meaning, excpet for --path (which defaults to pwd), the user will not be prompted with any quesiton - take the option where need to choose.

2. **Detection & Safety:**
   - Should the tool **detect existing configs** and warn before overwriting? for alpha - no
   - Should it create **backups** of existing files before modifying? no need - assume working in git project
   - Should it support a **dry-run mode** to preview changes? not for alpha - in the future

3. **Dependency Management:**
   - Should it check if the repo already has `requirements.txt`, `setup.py`, `pyproject.toml`, etc.? yes. check for many combinations.
   - How should it handle **migration** from existing dependency management (pip, poetry, etc.) to uv? leave this as an open question for later.

4. **Configuration Generation:**
   - Should configs be **opinionated defaults** or **customizable**? opinionated defaults for alpha. extendable in the future.
   - Should it read from a **config file** (e.g., `.pimp-my-repo.toml`) for repeatable setups?
   - Should it support **presets** (e.g., "minimal", "strict", "relaxed")? no need for start

5. **Execution Flow:**
   - Should it run the tools immediately after setup (e.g., run `ruff check` after installing)? yes - this is part of each tool migration, make sure it works.
   - Should it show a **summary** of what will be done before proceeding? no need for alpha
   - Should it support **partial runs** (e.g., only add ruff, skip everything else)? no need for alpha

## Supported Configs

### Core Features (from README):
- ✅ **uv** - Modern dependency management
- ✅ **ruff** - Linting and formatting
- ✅ **mypy** - Static type checking
- ✅ **pre-commit** - Git hooks
- ✅ **justfile** - Command runner
- ✅ **CI/CD** - GitHub Actions / GitLab CI

### Questions about configs:

1. **uv Integration:**
   - Should it create `pyproject.toml` if it doesn't exist? yes
   - Should it migrate existing `requirements.txt` to `uv` format? yes
   - Should it add `uv.lock` to `.gitignore`? no

2. **ruff Configuration:**
   - What **default rules** should be enabled/ignored? enable everything ("ALL")
   - Should it support different **line length** preferences? default to 120
   - Should it configure **ruff format** as well as linting? yes
   - ruff migration: run safe formatting and linting. For each existing error, add a matching `# noqa: <ERROR_ID>` next to the line.

3. **mypy Configuration:**
   - What **strictness level** (minimal, standard, strict)? strict - enable all features and checks
   - Should it configure **mypy.ini** or use `pyproject.toml`? use pyproject.toml
   - Should it add type stubs for common dependencies? yes

4. **pre-commit Hooks:**
   - Which hooks should be included by default? look at this project
   - Should it install hooks immediately or just create the config? create config + install
   - Should it support custom hooks? no

5. **justfile Commands:**
   - What commands should be included? (install, test, lint, format, type-check, etc.) look at this project for example
   - Should commands be **customizable** per project type? not for alpha
   - Should it detect existing `Makefile` and offer to migrate? yes, dont offer for alpha

6. **CI/CD:** - no CI feautre for alpha
   - Should it detect if it's a GitHub or GitLab repo automatically?
   - What **jobs** should be included? (test, lint, type-check, build, release?)
   - Should it support **matrix strategies** (multiple Python versions)?
   - Should it configure **dependabot/renovate** for dependency updates?

### Additional Features to Consider:

1. **Project Detection:**
   - Detect project type (library, application, package)?
   - Detect existing tools and suggest what's missing?

2. **Documentation:**
   - Generate/update `README.md` with usage instructions?
   - Add comments to generated configs explaining what they do?

3. **Validation:**
   - Validate that the repo is a valid Python project?
   - Check Python version compatibility?

4. **Rollback:**
   - Support undoing changes if something goes wrong? no - git state
   - Keep a log of what was changed? - yes, in state file

## Implementation Structure

### Proposed Architecture:
```
pimp_my_repo/
├── cli/
│   ├── __init__.py
│   ├── main.py          # Entry point, typer app
│   └── commands/        # Individual command modules
├── core/
│   ├── __init__.py
│   ├── detector.py      # Detect existing configs/tools
│   ├── generator.py    # Generate config files
│   └── installer.py    # Install/run tools
├── templates/           # Jinja2 templates for configs
│   ├── ruff.toml
│   ├── mypy.ini
│   ├── pre-commit.yaml
│   ├── justfile
│   └── ci/
│       ├── github.yml
│       └── gitlab.yml
└── models/
    ├── __init__.py
    └── config.py        # Pydantic models for config
```

## Questions for You:

1. **What's the primary use case?**
   - Quick setup for new projects?
   - Modernizing existing projects?
   - Both?

2. **How opinionated should it be?**
   - Very opinionated (one way to do things)?
   - Flexible (many options)?

3. **Should it be idempotent?**
   - Can you run it multiple times safely?
   - Should it update existing configs or skip them?

4. **Error handling:**
   - How should it handle failures?
   - Should it continue with other configs if one fails?

5. **Output:**
   - Should it be verbose by default?
   - Should it support quiet mode?
