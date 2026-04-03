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
    {{ RUN }} pre-commit install

install: install-dev lint cover-base

# Dependencies

lock:
    uv lock

lock-upgrade:
    uv lock --upgrade

check-lock:
    uv lock --check

# Test

test *args:
    {{ RUN }} python -m {{ PYTHON_TEST_COMMAND }} {{ args }}

test-fast:
    just test -s -q -m "smoke"

test-e2e-local name *args:
    just test -m "e2e_local" --fixture-name={{ name }} {{ args }}

test-e2e url rev="HEAD" *args:
    just test -m "e2e_remote" --e2e-url={{ url }} --e2e-rev={{ rev }} {{ args }}

cover-base *args:
    {{ RUN }} coverage run -m {{ PYTHON_TEST_COMMAND }} {{ args }}
    {{ RUN }} coverage report

cover-xml:
    just cover-base --junitxml=junit.xml -o junit_family=legacy
    {{ RUN }} coverage xml

cover-html: cover-base
    {{ RUN }} coverage html

cover-percentage:
    {{ RUN }} coverage report --precision 3 | grep TOTAL | awk '{print $4}' | sed 's/%//'

cover: cover-html
    {{ OPEN_FILE_COMMAND }} htmlcov/index.html &
    {{ DEL_COMMAND }} .coverage*

# Lint

format:
    {{ RUN }} ruff format

check-ruff:
    {{ RUN }} ruff format --check
    {{ RUN }} ruff check

check-mypy:
    {{ RUN }} dmypy run .

lint: format
    {{ RUN }} ruff check --fix --unsafe-fixes
    {{ RUN }} pre-commit run --all-files

# Packaging

build:
    {{ DEL_COMMAND }} -f dist/*
    uv build
    just lock

upload-test:
    {{ RUN }} twine upload --repository testpypi dist/*

upload:
    {{ RUN }} twine upload dist/*

build-and-upload: build upload

# CI

run-checks *args:
    {{ RUN }} scripts/run_checks.py {{ args }}

# Semantic release

semrel:
    @echo "Releasing version..."
    {{ RUN }} semantic-release version

semrel-dev:
    @echo "Releasing dev version..."
    {{ RUN }} semantic-release version --no-commit --no-push
    # Replace "-dev.1" with epoch time in version
    sed -i "s/-dev\.1/.dev.$(date +%s)/g" pyproject.toml
    just build
