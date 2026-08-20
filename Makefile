VENV ?= .venv
PY   := $(VENV)/bin/python

.PHONY: help venv install test test-unit test-integration test-contract lint fmt clean

help:
	@echo "venv              create $(VENV)"
	@echo "install           install glasswell and dev dependencies (editable)"
	@echo "test              full suite (unit + integration; integration needs docker)"
	@echo "test-unit         pure-function tier, no docker required"
	@echo "test-integration  ephemeral PostGIS tier"
	@echo "lint              ruff"
	@echo "fmt               ruff --fix"

venv:
	python3 -m venv $(VENV)

install: venv
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e '.[dev]'

test:
	$(PY) -m pytest tests -q

test-unit:
	$(PY) -m pytest tests -q -m unit

test-integration:
	$(PY) -m pytest tests -q -m integration

test-contract:
	$(PY) -m pytest tests -q -m contract

lint:
	$(PY) -m ruff check .

fmt:
	$(PY) -m ruff check . --fix

clean:
	rm -rf .pytest_cache .ruff_cache
	find src tests -name __pycache__ -type d -exec rm -rf {} +
