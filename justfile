# Variables

PYTHON_TEST_COMMAND := "pytest"
OPEN_FILE_COMMAND := "wslview"
DEL_COMMAND := "gio trash"
RUN := "uv run"

# Install

install-run:
	uv sync --no-default-groups

install-test:
	uv sync --no-default-groups --group test

install-all:
	uv sync --all-groups

install-dev: install-all
	{{RUN}} pre-commit install

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
	{{RUN}} python -m {{PYTHON_TEST_COMMAND}}

cover-base:
	{{RUN}} coverage run -m {{PYTHON_TEST_COMMAND}}
	{{RUN}} coverage report

cover-xml: cover-base
	{{RUN}} coverage xml

cover-html: cover-base
	{{RUN}} coverage html

cover-percentage:
	{{RUN}} coverage report --precision 3 | grep TOTAL | awk '{print $4}' | sed 's/%//'

cover: cover-html
	{{OPEN_FILE_COMMAND}} htmlcov/index.html &
	{{DEL_COMMAND}} .coverage*

# Lint

format:
	{{RUN}} ruff format

check-ruff:
	{{RUN}} ruff format --check
	{{RUN}} ruff check

check-mypy:
	{{RUN}} dmypy start || true
	{{RUN}} dmypy run .

lint: format
	{{RUN}} ruff check --fix --unsafe-fixes
	{{RUN}} pre-commit run --all-files

# Packaging

build:
	{{DEL_COMMAND}} -f dist/*
	uv build

upload-test:
	{{RUN}} twine upload --repository testpypi dist/*

upload:
	{{RUN}} twine upload dist/*

build-and-upload: build upload

# Semantic release

semrel:
	@echo "Releasing version..."
	{{RUN}} semantic-release version

semrel-dev:
	@echo "Releasing dev version..."
	{{RUN}} semantic-release version --no-commit --no-push
	# Replace "-dev.1" with epoch time in version
	sed -i "s/-dev\.1/.dev.$(date +%s)/g" pyproject.toml
	just build
