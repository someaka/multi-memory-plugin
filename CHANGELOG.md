# Changelog

All notable changes to the multi-memory plugin will be documented in this file.

The format is inspired by [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0] — 2026-05-29

### Added
- **5 new backend adapters**: OpenViking, Hindsight, RetainDB, ByteRover, Supermemory.
  All 9 Hermes memory providers are now supported.
- `_OpenVikingAdapter` — tools prefixed `viking_` (config key `openviking`)
- `_HindsightAdapter` — tools prefixed `hindsight_`
- `_RetainDBAdapter` — tools prefixed `retaindb_`
- `_ByteRoverAdapter` — tools prefixed `brv_` (config key `byterover`)
- `_SupermemoryAdapter` — tools prefixed `supermemory_`

### Fixed
- **HealthTracker now wired into lifecycle calls** — all lifecycle methods check
  `is_open()` before calling sub-providers and record success/failure. Backends
  that fail 3+ times consecutively are skipped (circuit breaker).
- **Silent exception swallowing** — all `except Exception: pass` blocks in lifecycle
  hooks now log at DEBUG level with backend name and error. No more invisible failures.
- **handle_tool_call prefix matching** — now uses adapter `PREFIX` attribute instead
  of `sub.name`, fixing routing for ByteRover (`brv_` vs `byterover`) and OpenViking
  (`viking_` vs `openviking`).
- **Fallback loop logging** — the fallback path in `handle_tool_call` now logs which
  backend was tried and why it failed.
- Hallucinated backends (Chroma, Pinecone, Weaviate, Qdrant, Milvus, Redis) removed
  from discovery, health_check, and tests — only real Hermes backends are listed.

### Changed
- `discovery.py`: `_BACKEND_REGISTRY` expanded from 4 to 9 entries
- `health_check.py`: `BACKENDS` dict expanded to cover all 9 backends
- `pyproject.toml`: version bumped to 0.4.0, added optional deps for new backends
- `plugin.yaml`: version bumped to 0.4.0, description updated
- All tests updated for 9 backends (204 tests, all passing)

## [0.3.0] — 2026-05-28

### Fixed
- `_MnemosyneAdapter`: uses Hermes plugin loader (`plugins.memory.load_memory_provider`)
  instead of `_try_import("mnemosyne")` which hit the pip MCP server package.
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

## [0.2.1] — 2026-05-28

### Fixed
- `__init__.py`: conditional imports for `tools.registry.tool_error` and
  `agent.memory_provider.MemoryProvider` — standalone fallbacks so the plugin
  works outside Hermes (testing, CI).
- `adapters.py`: `_try_import` catches `ModuleNotFoundError` from `find_spec`
  when parent package (e.g. `plugins`) is missing.
- `discovery.py`: `discover_backends` catches `ModuleNotFoundError` from `find_spec`.
- `pyproject.toml`: added `pyyaml>=6.0` to runtime deps, `test` optional-deps group.

## [0.2.0] — 2026-05-22

### Added
- Standalone repo extracted from Hermes agent monorepo.
- `plugin.yaml` — Hermes plugin metadata for discovery via `_ProviderCollector`.
- `pyproject.toml` — setuptools build config with optional dependency extras.
- `CONFIG.md` — full configuration reference.
- `CHANGELOG.md` — version history (this file).
- `scripts/install.sh` — idempotent one-command installer.
- `scripts/setup.sh` — interactive wizard.
- `scripts/health_check.py` — CLI health check per backend.
- `.github/workflows/ci.yml` — CI pipeline (Python 3.11–3.13).

## [0.1.0] — 2026-05-21

### Added
- `MultiMemoryProvider` — fans out lifecycle calls across active sub-providers.
- Four adapter classes: `_MnemosyneAdapter`, `_Mem0Adapter`, `_HolographicAdapter`,
  `_HonchoAdapter`.
- Tool name prefixing to avoid schema collisions.
- Dual config format support (`multi.backends` dict and `providers` list).
- Per-backend error isolation (try/except on every lifecycle call).
