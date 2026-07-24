# Changelog

All notable changes to the multi-memory plugin will be documented in this file.

The format is inspired by [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.10.0] — 2026-07-24

### Fixed — Canonical ABC Interface Alignment
- **`format_config_display()` → `get_status_config()`** — the plugin implemented
  a method Hermes never calls. ``hermes memory status`` calls
  ``get_status_config(provider_config) -> dict`` on the active provider. Renamed
  and changed return type from ``list[tuple[str,str]]`` to ``dict`` to match
  the canonical interface used by OpenViking and Supermemory providers.
- **`sync_turn` missing explicit `messages` parameter** — the ABC defines
  ``messages: Optional[List[Dict]] = None`` as a named keyword-only arg. The
  plugin hid it inside ``**kwargs``, meaning the adapter introspection
  ``_sync_accepts_messages()`` could fail to detect it on the multiplexer.
  Now explicitly declared on both ``MultiMemoryProvider`` and the standalone stub.

### Fixed — Robustness (Full Audit Passes 1–3)
- **`_renorm_schemas` KeyError on missing `name` key** — schemas without a
  `"name"` field now default to `""` instead of crashing. Also handles
  `None` values via `str()` coercion.
- **`_is_disabled` case sensitivity** — `"FALSE"`, `"NO"`, `"No"` now correctly
  disable backends via `.strip().lower()`. Previously only exact `"False"` matched.
- **`_get_active_backends` crash on non-dict `multi`/`backends`/`providers`**
  — added `isinstance` guards before all `.get()` calls. Malformed YAML
  config no longer causes `AttributeError`.
- **`_remove_backend_from_config` crash on non-dict `multi`/`backends`**
  — same isinstance guard pattern. Non-list `providers` coerced to `[]`.
- **`_cmd_remove` crash on non-dict config values** — added isinstance guards
  for `multi_cfg`, `backends_dict`, `providers_list`.
- **JSON status `config_format` crash on non-dict `multi`** — chained
  `.get("multi", {}).get("backends")` replaced with isinstance-checked access.
- **CLI schema field parsing** — `field["key"]` → `field.get("key")` with
  isinstance check. `choices` validated as list. `ref_map` guarded against `None`.
- **`pip_deps` validated as list** before iteration in dependency installer.
- **CI `pip install -r requirements.txt` guarded** — wrapped in `if [ -f ... ]`.

### Changed — Test Coverage and Documentation
- **Coverage: 88% → 97%** — 62 new tests added across 2 new test files
  (`test_fourth_pass.py`, `test_fifth_pass.py`). CLI coverage 71% → 99%.
  All `_cmd_update`, `_cmd_status` display branches, and `multi_command`
  dispatch paths now tested.
- **454 total tests** (was 392), all passing, `--cov-fail-under=90` passes.
- **`setup.cfg`** — added `[coverage:run]` and `[coverage:report]` sections
  with branch coverage and standard exclude patterns.
- **`RESEARCH_REPORT.md`** — updated stale `format_config_display` →
  `get_status_config` references and version `0.7.2` → `0.10.0`.
- **`AGENT.md`** — fixed key-files table (`_is_disabled` listed under
  `config.py` not `__init__.py`, added all test files to table, added
  `get_status_config()` to `__init__.py` row). Updated config precedence
  section to list all case-insensitive disable values.
- **`CONFIG.md`** — removed stale Chinese text, corrected `add` → `remove`
  in removal section.
- **`on_session_switch` missing explicit `rewound` parameter** — the ABC defines
  ``rewound: bool = False`` as a named keyword-only arg. The plugin hid it
  inside ``**kwargs``. Now explicitly declared and forwarded to all subs.

### Changed
- **CLI `format_config_display` reference** updated to call ``get_status_config``
  with proper dict iteration for display output.
- **Standalone stub `sync_turn`** now matches ABC signature exactly:
  ``(*, session_id="", messages=None, **kwargs)`` instead of bare ``**kwargs``.

### Changed — Code Quality (Audit Pass 4)
- **Removed vestigial `[flake8]` config** from `setup.cfg`. The project uses
  ruff exclusively (CI, CONTRIBUTING.md, AGENT.md all reference ruff). The
  flake8 section implied a linter that isn't installed or run.
- **Python 3.14 added to CI matrix**. `pyproject.toml` declares
  `requires-python = ">=3.10"` with no upper bound; CI now tests 3.10–3.14.
- **mypy type checking added to CI** as a dedicated job. The codebase uses
  type hints extensively; mypy now validates them at CI time. Fixed 3 type
  errors surfaced by the initial run (`installed_backends` return type,
  `desc` coercion to `str`, removed stale `type: ignore` comments).
- **`conftest.py` hardcoded paths → `HERMES_AGENT_PATH` env var**. Developers
  with a hermes-agent checkout outside `~/.hermes/` or `/tmp/` can now set
  `HERMES_AGENT_PATH` instead of having `@requires_holographic` tests silently
  skipped. CI already sets this var.
- **Cache field init centralized** via `_SubProviderAdapter._init_caches()`.
  `_GenericAdapter` and `_MnemosyneAdapter` previously duplicated cache field
  assignments when bypassing the base `__init__`. Both now call `_init_caches()`
  — adding a new cached field requires updating one method, not three sites.
- **Mnemosyne plugin dir names centralized** in `MNEMOSYNE_PLUGIN_DIRS`
  constant. Previously hardcoded in both `adapters.py` and `discovery.py`;
  now both import the single constant.

## [0.9.0] — 2026-07-20

### Added
- **`backup_paths()` fan-out** — `MultiMemoryProvider` merges and deduplicates
  external paths from all sub-providers so `hermes backup` captures them.
- **`get_config_schema()` / `save_config()` on adapters and provider** —
  `hermes memory setup` no longer hits `AttributeError` or silent "no config".
- **`load_full_config()` in `config.py`** — single config reader; `__init__.py`
  no longer opens YAML directly.
- **`rewound` parameter** on `on_session_switch` stub and forwarded via `**kwargs`.
- **Standalone stub parity** — stub `MemoryProvider` now has `backup_paths()`,
  `get_config_schema()`, `save_config()`, `rewound`.
- **27 new API-parity tests** (`test_api_parity.py`) and **33 second-pass tests**
  (`test_second_pass.py`) covering backup_paths, rewound, JSON error contract,
  close() fallback, config schema forwarding, batch shutdown, and config guards.

### Changed
- **`tool_error` standalone fallback returns JSON** — matches the real Hermes
  `tools.registry.tool_error` contract (`{"error": "..."}`).
- **`_batch_shutdown` replaces `_close_or_shutdown`** — one shared
  `ThreadPoolExecutor` for all subs instead of one executor per sub.
  Empty input is a no-op. Timeout and per-sub error isolation preserved.
- **`get_tool_schemas()` uses double-checked locking** — cache read/write
  under `self._lock`; expensive delegate calls happen outside the lock.
- **`_invalidate_schema_cache()` acquires the lock** — prevents TOCTOU race
  with concurrent `get_tool_schemas()`.
- **`_loading` guard initialized in `__init__`** — removed `getattr` hack.
- **`_normalise_multi_config` → `_normalize_multi_config`** — consistent
  American English naming.
- **`_RetainDBAdapter.close()` override removed** — base class now has the
  same `close()` → `shutdown()` fallback.
- **CI: Python 3.10 added** to matrix (matches `requires-python >= 3.10`).
- **CI: hermes-agent pinned** to `v2026.7.7.2` for API stability.
- **CI: silent failure removed** — `pip install -r requirements.txt` errors
  are now visible.

### Fixed
- **`_normalise_multi_config` crash** on non-dict `multi:` values
  (e.g. `multi: "string"`) — added `isinstance` guard.
- **`_is_disabled` docstring** corrected — `{}` is truthy (enabled), not
  disabled as the old docstring implied.
- **`_MnemosyneAdapter` truthy check** — removed always-true
  `getattr(provider, "name", dirname)` condition.
- **Dead `import yaml`** removed from `__init__.py` (config reading
  consolidated into `config.py`).
- **Dead `_loading_config = False`** module-level variable removed.
- **Duplicate `plugin.yaml`** at repo root removed (canonical copy is
  `src/multi_memory/plugin.yaml`).
- **README badge** updated to Python 3.10+.
- **CONTRIBUTING/AGENT.md** updated for CI changes and removed stale
  `_close_or_shutdown` reference.

## [0.8.0] — 2026-06-08

### Changed
- **Removed HealthTracker entirely** — no failure counting, no exclusion,
  no retry logic. The installed backends list is the truth. Errors are
  logged at load time. If a backend fails to load, it's not in the list.
- **`_MnemosyneAdapter` fails loud** — raises `RuntimeError` with install
  instructions instead of silent `super().__init__()` fallback when
  mnemosyne plugin is not installed.
- **CI upgraded** — `actions/checkout@v6`, `actions/setup-python@v6`,
  `astral-sh/ruff-action@v1`. Lint and test split into separate jobs.
  Removed `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24` hack.
- **Documentation full pass** — removed all stale circuit breaker references
  from README, CONFIG.md, CONTRIBUTING.md, AGENT.md.

### Fixed
- Duplicate `getattr`/`callable` block in `_fan_out` (dead code from prior merge).
- `test_cli.py` — properly mocks `builtins.__import__` for plugin discovery test.

## [0.7.2] — 2026-06-06

### Added
- **Interactive setup wizard (`hermes multi setup`)** — ported the full curses-based
  memory backend configuration UX from the hermes-agent fork. Includes:
  - `hermes multi setup` — interactive picker for adding/removing backends
  - `hermes multi setup <name>` — per-backend field-by-field config (API keys,
    model choices, endpoints)
  - Dependency auto-install from provider `plugin.yaml` (uv/pip)
  - Env var management — writes secrets to `~/.hermes/.env` with 0600 permissions
  - "Add alongside" vs "Replace all" prompt when backends are already active
  - Curses-based pickers with terminal fallbacks for non-curses environments
- **Rich status display** — `hermes multi status` now shows per-backend health,
  config, env var status, and plugin installation state
- **Backend discovery** — auto-discovers installed memory providers via the
  Hermes plugin system (with static registry fallback for standalone use)

### Changed
- **CLI docs** — README, CONFIG.md, AGENT.md, and CONTRIBUTING.md updated to
  promote `hermes multi setup` over manual `hermes config set` commands
- **CONTRIBUTING.md** — setup instructions use `uv` instead of `pip install -e`

### Fixed
- **Plugin invisible in `hermes plugins list` and dashboard (regression)** —
  v0.7.1 removed the general plugin symlink at `~/.hermes/plugins/multi/`
  which the dashboard and `hermes plugins list` require for discovery.
  Restored with `kind: standalone` in plugin.yaml which prevents the
  `kind=exclusive` auto-coercion that the removal was trying to avoid.
- **`logging.debug` used instead of `logger.debug` in cli.py** — discovery
  failure messages were logged under the root logger instead of the module
  logger. Added missing `logger = logging.getLogger(__name__)`.
- **Tool budget warning fires on every load** — raised `DEFAULT_THRESHOLD`
  from 20 to 40 because mnemosyne alone registers 23 tools (two backends
  easily exceed 20).
- **`_is_disabled()` didn't handle empty-string YAML values** — an empty
  string value in `multi.backends` was treated as enabled. Now recognizes
  empty strings, strings with only whitespace, and edge cases from
  `0` as int (in addition to the existing str check).

## [0.7.0] — 2026-06-05

### Fixed
- **Plugin invisible in `hermes plugins list` and dashboard** — install script
  now creates a second symlink at `~/.hermes/plugins/multi/` for the general
  plugin scanner (CLI commands, dashboard visibility). Previously only created
  a symlink in the memory discovery path which the general scanner skips.
- **Auto-detection marked plugin as `kind=exclusive`** — added explicit
  `kind: standalone` to `plugin.yaml` so the general plugin scanner doesn't
  auto-detect the plugin as a memory provider and skip it entirely.
- **`hermes multi add <backend>` set wrong provider** — was setting
  `memory.provider` to the backend name (e.g. `mnemosyne`) instead of `multi`.
- **`_cmd_remove` left broken config** — removing the last backend now resets
  `memory.provider` back to `default` instead of leaving it as `multi` with
  zero backends.
- **`register()` crashed on older Hermes** — wrapped CLI registration in
  `hasattr(ctx, 'register_cli_command')` guard for graceful degradation.
- **`get_tool_schemas()` held lock during delegate calls** — now takes a
  snapshot first (consistent with `_fan_out()`) to avoid contention in
  gateway mode.
- **Install script used `python` instead of `$PYTHON`** — test runner step
  now uses the detected Python binary.
- **Install script `yaml.dump` destroyed config comments** — replaced with
  `hermes config set` which preserves YAML structure.
- **Version mismatch** — aligned plugin.yaml (was 0.6.0), pyproject.toml
  (was 0.4.0), and scripts (were 0.3.0) to 0.7.0.
- **Install script display bug** — `MultiMemoryProvider.name` property was
  printed on the uninstantiated class, showing `<property object at 0x...>`.
- **Missing `PYTHON` variable in install script** — auto-config steps failed
  with `unbound variable`.

### Added
- **CLI registration via general plugin system** — `register()` now calls
  `ctx.register_cli_command()` so `hermes multi` commands appear in
  `hermes plugins list` and the dashboard even before `memory.provider: multi`
  is configured.
- **Backend name validation** — `hermes multi add` now validates the backend
  name against known backends and suggests valid alternatives.
- **`_cmd_status` shows installation status** — displays whether each active
  backend is installed, missing, or unknown.
- **Install script auto-configuration** — `install.sh` now automatically
  enables the plugin in `plugins.enabled` and sets `memory.provider: multi`.
- **Dual-symlink install architecture** — documented and implemented the
  two-symlink pattern for memory discovery + general plugin scanner.

## [0.6.0] — 2026-05-31

### Added
- **Runtime sub-provider management** — `add_provider()` and `remove_provider()`
  methods for adding/removing sub-providers at runtime with proper shutdown,
  health reset, and thread safety.
- **`get_provider(name)`** — lookup sub-provider by name.
- **`providers` property** — list of active sub-provider names.
- **`get_all_tool_names()`** / **`has_tool()`** — tool introspection methods.
- **`on_session_switch` empty guard** — matches fork behavior (skip empty session IDs).
- **Metadata write mode introspection** — `_metadata_write_mode()` detects
  keyword/positional/legacy signatures on delegates for `on_memory_write`.
- **Sync messages introspection** — `_sync_accepts_messages()` detects if
  delegate's `sync_turn` accepts a `messages` keyword.
- **Holographic double-prefix fix** — `_HolographicAdapter` now uses
  strip-then-re-add pattern (like all other adapters) to prevent
  `holographic_holographic_store` when upstream returns prefixed names.
- **Core integration spec** — `CORE-INTEGRATION-SPEC.md` defines the 7 minimal
  core changes needed for full fork replacement.

## [0.5.0] — 2026-05-31

### Added
- **Thread safety** — `MultiMemoryProvider` lifecycle dispatch is now protected by
  `threading.RLock`. All methods snapshot the sub-provider list under the lock
  before dispatching, preventing crashes in concurrent gateway mode.
- **Schema failure protection** — `get_tool_schemas()` wraps each sub-adapter in
  try/except. A broken backend's schemas are skipped (with health failure recorded)
  instead of crashing all memory tools (fixes #9948 pattern).
- **RetainDB `close()` delegation** — `_RetainDBAdapter` and base `_SubProviderAdapter`
  now delegate `close()` for proper SQLite thread-local connection cleanup.
  `MultiMemoryProvider.shutdown()` prefers `close()` over `shutdown()`.
- **Legacy config format** — `config.py:get_enabled_backends()` now reads
  `memory.provider` string (single-provider) in addition to `memory.providers` list
  and `multi.backends` dict. Config priority: `multi.backends` > `providers` list >
  `provider` string.
- 16 new tests covering thread safety, schema failure protection, close() delegation,
  and legacy config format.

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
