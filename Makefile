VENV   ?= .venv
PY     := $(VENV)/bin/python
DOCKER ?= docker
# Every container and volume tests/conftest.py creates carries this label, so the sweep below
# can find them without touching anything else on the host.
TEST_LABEL ?= glasswell.test

.PHONY: help venv install test test-unit test-integration test-e2e lint fmt clean prune-test-volumes

help:
	@echo "venv              create $(VENV)"
	@echo "install           install glasswell and dev dependencies (editable)"
	@echo "test              full suite (unit + integration; integration needs docker)"
	@echo "test-unit         pure-function tier, no docker required"
	@echo "test-integration  ephemeral PostGIS tier"
	@echo "test-e2e          browser path against \$$GLASSWELL_BASE_URL (needs a key)"
	@echo "prune-test-volumes  reclaim volumes a killed test session left behind"
	@echo "lint              ruff"
	@echo "fmt               ruff --fix"

venv:
	python3 -m venv $(VENV)

install: venv
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e '.[dev]'

test: prune-test-volumes
	$(PY) -m pytest tests -q

test-unit:
	$(PY) -m pytest tests -q -m unit

test-integration: prune-test-volumes
	$(PY) -m pytest tests -q -m integration

# DR-25/N-10: the session fixture removes its own volume, but a killed session cannot.
# Two agents filled /home to 100% this way in one day, so the reclaim is not a manual step.
prune-test-volumes:
	-@$(DOCKER) volume prune -af --filter label=$(TEST_LABEL) 2>/dev/null | tail -1  # no docker is not a test failure

# Its own npm project on purpose: playwright-core must not enter the web bundle's lockfile.
test-e2e:
	@[ -d tests/e2e/node_modules ] || npm --prefix tests/e2e ci --no-audit --no-fund
	node tests/e2e/smoke.mjs

lint:
	$(PY) -m ruff check .

fmt:
	$(PY) -m ruff check . --fix

clean:
	rm -rf .pytest_cache .ruff_cache
	find src tests -name __pycache__ -type d -exec rm -rf {} +
