.PHONY: install format test check build clean

install:
	poetry install

format:
	poetry run black src tests

lint:
	poetry run black --check src tests

test:
	poetry run pytest tests -v

check: format test

build:
	poetry build

clean:
	rm -rf dist .pytest_cache __pycache__ src/**/__pycache__ tests/__pycache__
