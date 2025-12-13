# Variables

PYTHON_TEST_COMMAND := "pytest"
OPEN_FILE_COMMAND := "wslview"
DEL_COMMAND := "gio trash"

# Install

install-run:
	uv sync --no-default-groups

install-test:
	uv sync --no-default-groups --group test

install-all:
	uv sync --all-groups

install-dev: install-all
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

cover-percentage:
	uv run coverage report --precision 3 | grep TOTAL | awk '{print $4}' | sed 's/%//'

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

# Packaging

build:
	{{DEL_COMMAND}} -f dist/*
	uv build

upload-test:
	uv run twine upload --repository testpypi dist/*

upload:
	uv run twine upload dist/*

build-and-upload: build upload

# Semantic release

semrel:
	@echo "Releasing version..."
	uv run semantic-release version

semrel-dev:
	@echo "Releasing dev version..."
	uv run semantic-release version --no-commit --no-push
	# Replace "-dev.1" with epoch time in version
	sed -i "s/-dev\.1/.dev.$(date +%s)/g" pyproject.toml
	just build
