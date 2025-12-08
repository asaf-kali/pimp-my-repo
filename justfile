# Variables

PYTHON_TEST_COMMAND := "pytest"
OPEN_FILE_COMMAND := "wslview"
DEL_COMMAND := "gio trash"

# Install

install-run:
	uv sync --no-default-groups

install-test:
	uv sync --no-default-groups --group test

install-dev:
	uv sync --all-groups
	uv run pre-commit install

install: install-dev lint cover-base

# UV

lock:
	uv lock

lock-upgrade:
	uv lock --upgrade

lock-check:
	uv lock --check

# Test

test:
	uv run python -m {{PYTHON_TEST_COMMAND}}

cover-base:
	uv run coverage run -m {{PYTHON_TEST_COMMAND}}
	uv run coverage report

cover-xml: cover-base
	uv run coverage xml

cover-html: cover-base
	uv run coverage html

cover: cover-html
	{{OPEN_FILE_COMMAND}} htmlcov/index.html &
	{{DEL_COMMAND}} .coverage*

# Lint

format:
	uv run ruff format
	uv run ruff check --fix --unsafe-fixes

check-ruff:
	uv run ruff format --check
	uv run ruff check

check-mypy:
	uv run mypy .

lint: format
	uv run pre-commit run --all-files
