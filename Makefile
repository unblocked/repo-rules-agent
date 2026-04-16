.PHONY: install format lint test check build clean

install:
	uv sync

format:
	uv run ruff format src tests

lint:
	uv run ruff format --check src tests
	uv run ruff check src tests

test:
	uv run pytest tests -v

check: format test

build:
	uv build

clean:
	rm -rf dist .pytest_cache __pycache__ src/**/__pycache__ tests/__pycache__
