SHELL := /bin/bash
UV := $(shell command -v uv 2>/dev/null || echo $(HOME)/.local/bin/uv)

.DEFAULT_GOAL := help

.PHONY: help setup install test coverage lint format docs docs-serve mcp-test compile check clean

help:
	@echo "Available targets:"
	@echo "  setup      - Create a local virtual environment"
	@echo "  install    - Sync project and development dependencies"
	@echo "  test       - Run unit tests"
	@echo "  coverage   - Run tests with coverage"
	@echo "  lint       - Run ruff lint"
	@echo "  format     - Auto-format and auto-fix with ruff"
	@echo "  docs       - Build the MkDocs site in strict mode"
	@echo "  docs-serve - Run the local documentation preview server"
	@echo "  mcp-test   - Smoke-test the configured Hermes Zulip MCP server"
	@echo "  compile    - Compile-check Python modules"
	@echo "  check      - Run lint, tests, compile, and MCP smoke test"
	@echo "  clean      - Remove local build/test caches"

setup:
	$(UV) venv .venv --python 3.13 --allow-existing

install: setup
	$(UV) sync --dev

test: install
	$(UV) run python -m pytest -q

coverage: install
	$(UV) run python -m pytest --cov=zulip_hermes --cov-report=term-missing --cov-report=xml

lint: install
	$(UV) run ruff check .

format: install
	$(UV) run ruff check --fix .
	$(UV) run ruff format .

docs:
	$(UV) sync --group docs
	$(UV) run --group docs mkdocs build --strict

docs-serve:
	$(UV) sync --group docs
	$(UV) run --group docs mkdocs serve

compile: install
	$(UV) run python -m compileall main.py zulip_hermes zulip_mcp.py zulip_hermes_bot.py zulip_query.py

mcp-test: install
	hermes mcp test zulip

check: lint test compile docs mcp-test

clean:
	rm -rf build dist site *.egg-info .pytest_cache .ruff_cache .coverage coverage.xml htmlcov
