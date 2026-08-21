VENV   ?= .venv
PY     := $(VENV)/bin/python
DOCKER ?= docker
# DIR-14: anvil is the lab's CI host and the default for full suites. This workstation runs
# single files while iterating. `anvil` is resolved by name because its lease moves.
ANVIL_HOST     ?= tcp://anvil:2376
DOCKER_CERTS   ?= $(HOME)/.docker/tls
ANVIL_ENV      := DOCKER_HOST=$(ANVIL_HOST) DOCKER_TLS_VERIFY=1 DOCKER_CERT_PATH=$(DOCKER_CERTS) \
                  GLASSWELL_REQUIRE_DOCKER=1
# Every container and volume tests/conftest.py creates carries this label, so the sweep below
# can find them without touching anything else on the host.
TEST_LABEL ?= glasswell.test

.PHONY: help venv install test test-anvil test-local test-unit test-integration test-e2e \
        dbtier-preflight serve-branch changelog \
        lint fmt clean prune-test-volumes check-workstation snapshot

help:
	@echo "venv              create $(VENV)"
	@echo "install           install glasswell and dev dependencies (editable)"
	@echo "test              full suite against whichever daemon is configured"
	@echo "test-anvil        full suite on anvil — the default for a full run (DIR-14)"
	@echo "test-local        full suite on this workstation's daemon"
	@echo "dbtier-preflight  check a remote daemon's path can carry the database tiers"
	@echo "test-unit         pure-function tier, no docker required"
	@echo "test-integration  ephemeral PostGIS tier"
	@echo "test-e2e          browser path against \$$GLASSWELL_BASE_URL (needs a key)"
	@echo "prune-test-volumes  reclaim volumes a killed test session left behind"
	@echo "check-workstation   flag glasswell persistent state on a workstation"
	@echo "serve-branch      ephemeral PostGIS + seeds + uvicorn for a branch (GW_ROOT=...)"
	@echo "changelog         fold changelog.d/ fragments into CHANGELOG.md (TITLE=\"...\")"
	@echo "lint              ruff"
	@echo "fmt               ruff --fix"
	@echo "snapshot          rewrite tests/contract/openapi_snapshot.json from the document"

venv:
	python3 -m venv $(VENV)

install: venv
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e '.[dev]'

test: prune-test-volumes
	$(PY) -m pytest tests -q

# The suite reaches a remote daemon through published ports rather than the bridge network;
# tests/conftest.py:daemon_address is where that branch is taken. The preflight goes first
# because a reachable daemon says nothing about whether the path can carry a bulk transfer.
test-anvil: dbtier-preflight
	@$(ANVIL_ENV) $(MAKE) --no-print-directory test

dbtier-preflight:
	@$(ANVIL_ENV) $(PY) -m tests.support.dbtier_preflight

test-local: test

check-workstation:
	@scripts/workstation-hygiene.sh

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

# A gate that judges a branch needs the branch's own API under the browser, not the
# deployed instance's; tests/e2e/README.md explains the GW_* knobs.
serve-branch:
	$(PY) tests/support/serve_branch.py

# Tracks write changelog.d/<branch>-<slug>.md; only the integrator folds. changelog.d/README.md.
changelog:
	$(PY) scripts/changelog-assemble.py --title "$(TITLE)"

# A generated artifact with no in-tree regeneration path is one an agent repairs by hand.
snapshot:
	$(PY) scripts/regen-snapshot.py

clean:
	rm -rf .pytest_cache .ruff_cache
	find src tests -name __pycache__ -type d -exec rm -rf {} +
