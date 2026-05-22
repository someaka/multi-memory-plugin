# ──────────────────────────────────────────────────────────
# Makefile — multi-memory plugin
# ──────────────────────────────────────────────────────────

.PHONY: install test lint clean coverage install-hook

SHELL := /usr/bin/env bash
PACKAGE := multi_memory

install:
	pip install -e ".[all]"

test:
	python -m pytest tests/ -v

lint:
	python -m flake8 src/$(PACKAGE)/ tests/

coverage:
	python -m pytest tests/ --cov=src/$(PACKAGE)/ --cov-report=term-missing

clean:
	rm -rf .coverage .pytest_cache/ htmlcov/ *.egg-info/ __pycache__/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete

install-hook:
	@echo "Installing pre-commit hook (flake8 + pytest)..."
	@printf '#!/usr/bin/env bash\nset -euo pipefail\necho "Running flake8..."\npython -m flake8 src/ tests/\necho "Running tests..."\npython -m pytest tests/ -q\n' > .git/hooks/pre-commit
	@chmod +x .git/hooks/pre-commit
	@echo "OK"
