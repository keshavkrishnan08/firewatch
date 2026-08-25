# FIREWATCH — reproducible entrypoints.
# All headline artifacts regenerate from pinned public snapshots via `make replay`.

PYTHON ?= .venv/bin/python
PIP    ?= .venv/bin/pip
FIRE   ?= demo

.PHONY: help setup install install-all test test-fast lint fmt api web replay ingest forecast demo clean

help:
	@echo "FIREWATCH make targets:"
	@echo "  setup        create .venv and install core deps"
	@echo "  install-all  install every optional extra (geo, sat, osm, perception)"
	@echo "  test         run the full test suite"
	@echo "  lint         ruff static checks"
	@echo "  fmt          ruff auto-format"
	@echo "  api          run the FastAPI backend (http://localhost:8000)"
	@echo "  web          run the frontend dev server (http://localhost:5173)"
	@echo "  replay FIRE=<id>   regenerate the full picture for one fire (default: demo)"
	@echo "  demo         build the self-contained demo event and run the replay"

setup:
	python3 -m venv .venv
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"

install-all:
	$(PIP) install -e ".[dev,geo,sat,osm,perception,accel]"

test:
	$(PYTHON) -m pytest

test-fast:
	$(PYTHON) -m pytest -m "not slow"

lint:
	$(PYTHON) -m ruff check src tests

fmt:
	$(PYTHON) -m ruff format src tests
	$(PYTHON) -m ruff check --fix src tests

api:
	$(PYTHON) -m uvicorn firewatch.api.server:app --reload --port 8000

web:
	cd web && npm install && npm run dev

# Reproduce the full picture for one fire from pinned public snapshots.
# Regenerates: live COP state, georeferenced camera fronts, assimilation ON/OFF
# ablation, calibration diagrams, and the retrospective lead-time delta.
replay:
	$(PYTHON) -m firewatch.api.replay --fire $(FIRE)

# Build the fully-offline synthetic demo event (no network / no keys needed),
# then run the reproducible replay over it end-to-end.
demo:
	$(PYTHON) -m firewatch.cli build-demo --fire demo
	$(PYTHON) -m firewatch.api.replay --fire demo

ingest:
	$(PYTHON) -m firewatch.cli ingest --fire $(FIRE)

forecast:
	$(PYTHON) -m firewatch.cli forecast --fire $(FIRE)

clean:
	rm -rf outputs/* data/events/$(FIRE)/cache 2>/dev/null || true
