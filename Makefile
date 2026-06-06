# ──────────────────────────────────────────────────────────
# Makefile — multi-memory plugin
# ──────────────────────────────────────────────────────────

.PHONY: install test lint ruff clean coverage install-hook

SHELL := /usr/bin/env bash
PACKAGE := multi_memory

install:
	uv sync --extra test

PYTHON ?= python3
HERMES_AGENT ?= $(HOME)/.hermes/hermes-agent
PYTEST_ARGS ?= -v

# Auto-detect hermes-agent path for PYTHONPATH (needed by bundled memory
# plugins like holographic).  Falls back to ~/.hermes/hermes-agent.
HERMES_PATH := $(shell \
  if [ -d "$(HERMES_AGENT)" ]; then echo "$(HERMES_AGENT)"; \
  elif [ -d "/tmp/hermes-agent" ]; then echo "/tmp/hermes-agent"; \
  else echo ""; fi)

test:
	PYTHONPATH="$(HERMES_PATH):src" uv run pytest tests/ $(PYTEST_ARGS)

lint: ruff
	$(PYTHON) -m flake8 src/$(PACKAGE)/ tests/

ruff:
	$(PYTHON) -m ruff check src/ tests/

coverage:
	PYTHONPATH="$(HERMES_PATH):src" uv run pytest tests/ --cov=src/$(PACKAGE)/ --cov-report=term-missing

clean:
	rm -rf .coverage .pytest_cache/ htmlcov/ *.egg-info/ __pycache__/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete

install-hook:
	@echo "Installing pre-commit hook (ruff + pytest)..."
	@printf '#!/usr/bin/env bash\nset -euo pipefail\necho "Running ruff..."\nuv run ruff check src/ tests/\necho "Running tests..."\nuv run pytest tests/ -q\n' > .git/hooks/pre-commit
	@chmod +x .git/hooks/pre-commit
	@echo "OK"
