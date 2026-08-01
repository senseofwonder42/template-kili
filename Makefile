.DEFAULT_GOAL := help
.PHONY: help setup lint format test clean

help: ## Show this help
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  %-10s %s\n", $$1, $$2}'

setup: ## Install dependencies and git hooks
	uv sync
	uv run pre-commit install

lint: ## Check style and lint rules
	uv run ruff check
	uv run ruff format --check

format: ## Fix lint issues and format the code
	uv run ruff check --fix
	uv run ruff format

test: ## Run the test suite
	uv run pytest

clean: ## Remove caches and build artifacts
	rm -rf .pytest_cache .ruff_cache .mypy_cache build dist
	find . -type d -name __pycache__ -not -path './.venv/*' \
		-exec rm -rf {} +
