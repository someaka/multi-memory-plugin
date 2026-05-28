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

## [0.3.0] — 2026-05-28

### Fixed
- `_MnemosyneAdapter`: uses Hermes plugin loader (`plugins.memory.load_memory_provider`)
  instead of `_try_import("mnemosyne")` which hit the pip MCP server package.
  Mnemosyne is a user-installed plugin at `~/.hermes/plugins/mnemosyne/`.
- `_MnemosyneAdapter`: `handle_tool_call` passes full prefixed tool names
  (`"mnemosyne_recall"`) since Mnemosyne dispatches on full names internally.
- `_MnemosyneAdapter`: `get_tool_schemas` returns schemas directly from delegate
  (Mnemosyne already prefixes its own tools — no double-prefix).
- `_Mem0Adapter`: `get_tool_schemas` strips existing `"mem0_"` prefix before
  re-adding it, preventing `mem0_mem0_profile` double-prefix.
- `_Mem0Adapter`: `handle_tool_call` passes full prefixed names (`"mem0_search"`)
  since Mem0 dispatches on full names internally.
- `_HonchoAdapter`: same double-prefix fix as Mem0 — strips then re-adds prefix.
- `_HonchoAdapter`: `handle_tool_call` passes full prefixed names.
- `discovery.py`: Mnemosyne detection uses plugin loader check instead of
  `find_spec("mnemosyne")` which found the pip MCP server.
- `health_check.py`: Mnemosyne detection uses plugin loader; Mem0 env check
  also reads `~/.hermes/mem0.json` for API key.

### Tests
- **184 tests** (up from 183), all passing.
- Added `TestNoDoublePrefix` (5 tests): verifies Mem0, Honcho, Holographic,
  and Mnemosyne adapters produce correctly prefixed tool names without duplication.
- Updated `test_discovery.py`: all tests use mock-based plugin loader checks
  instead of `find_spec("mnemosyne")`.
- Removed unused `pytest` import from `test_discovery.py`.

### Docs
- README.md: updated "How it works" diagram to show correct prefix handling.
- README.md: added notes about per-adapter prefix strategies.
- CONFIG.md: updated Mnemosyne and Mem0 backend descriptions.

## [0.2.1] — 2026-05-28

### Fixed
- `__init__.py`: conditional imports for `tools.registry.tool_error` and
  `agent.memory_provider.MemoryProvider` — standalone fallbacks so the plugin
  works outside Hermes (testing, CI).
- `adapters.py`: `_try_import` catches `ModuleNotFoundError` from `find_spec`
  when parent package (e.g. `plugins`) is missing.
- `discovery.py`: `discover_backends` catches `ModuleNotFoundError` from `find_spec`.
- `pyproject.toml`: added `pyyaml>=6.0` to runtime deps, `test` optional-deps group.
- CI: install test deps (`pip install -e ".[all,test]"`).

### Changed
- Removed redundant `name: str = "multi"` class attribute (property already provides it).
- Removed unused `Any` import from `validate.py`.
- Added `-> None` return type hint to `register()`.
- Added comment on `_MnemosyneAdapter.name` property explaining the override.

### Tests
- **154 tests** (up from 131), **99% coverage** (up from 94%).
- Added `TestSubProviderAdapterDelegation` (16 mock-based tests for adapter delegation).
- Added `TestRegisterFunction`, `TestLoadConfigEdgeCases`, `TestNamePropertyConsistency`.
- Extracted `_holographic_available()` to `conftest.py` (was duplicated in 2 files).
- Replaced fragile generator-throw exception patterns with `side_effect`.
- Replaced `importlib.reload()` in config tests with `mock.patch`.
- Mock-based `provider` fixture (no real backends required).
- `requires_holographic` skip marker for tests needing Hermes plugins package.
- 16 unit tests covering config parsing, backend loading, and routing.