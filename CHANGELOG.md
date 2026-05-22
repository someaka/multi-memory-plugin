# Changelog

All notable changes to the multi-memory plugin will be documented in this file.

The format is inspired by [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] — 2026-05-22

### Added
- Standalone repo extracted from Hermes agent monorepo.
- `plugin.yaml` — Hermes plugin metadata for discovery via `_ProviderCollector`.
- `pyproject.toml` — setuptools build config with optional dependency extras.
- `setup.cfg` — flake8 and pytest defaults.
- `Makefile` — convenience targets for install, test, lint, clean, coverage.
- `CONFIG.md` — full configuration reference covering both config formats and
  per-backend options.
- `CHANGELOG.md` — version history (this file).
- `scripts/install.sh` — idempotent one-command installer (symlink + validate + test).
- `scripts/setup.sh` — interactive wizard that discovers installed backends and
  writes config.yaml.
- `scripts/health_check.py` — CLI health check per backend, with `--json` output
  and graceful handling of missing backends.
- `.github/workflows/ci.yml` — CI pipeline (Python 3.11–3.13 on ubuntu-latest).

### Changed
- `src/multi_memory/` — original plugin code extracted from Hermes monorepo
  `plugins/memory/multi/` to standalone package.
- `README.md` — updated install instructions for standalone repo.

## [0.1.0] — 2026-05-21

### Added
- `MultiMemoryProvider` — fans out lifecycle calls across active sub-providers.
- Four adapter classes: `_MnemosyneAdapter`, `_Mem0Adapter`, `_HolographicAdapter`,
  `_HonchoAdapter`.
- Tool name prefixing (`mnemosyne_`, `mem0_`, etc.) to avoid schema collisions.
- Dual config format support (`multi.backends` dict and `providers` list).
- Per-backend error isolation (try/except on every lifecycle call).
- 16 unit tests covering config parsing, backend loading, and routing.
