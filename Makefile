.PHONY: install fmt lint type test cov run ui-dev clean gates

install:
	python -m pip install --upgrade pip
	pip install -e ".[dev]"
	pre-commit install

fmt:
	ruff format src tests
	ruff check --fix src tests

lint:
	ruff check src tests
	ruff format --check src tests

type:
	mypy src

test:
	pytest -q

cov:
	pytest --cov=src/mercari_alert_bot --cov-report=term-missing

gates: lint type test

run:
	python -m mercari_alert_bot

ui-dev:
	uvicorn mercari_alert_bot.web.app:create_app --factory --reload --port 8080

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
