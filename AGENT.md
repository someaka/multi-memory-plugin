# AGENT.md

Instructions for AI coding assistants working on the multi-memory plugin.

## Overview

This is a standalone Hermes Agent plugin that runs multiple memory backends
simultaneously. It lives in `src/multi_memory/` and is installed into Hermes
at `~/.hermes/hermes-agent/plugins/memory/multi/`.

The plugin implements the `MemoryProvider` ABC from `agent.memory_provider` in
the Hermes core. It fans lifecycle calls across active sub-providers with
per-provider error isolation, and
thread-safe dispatch.

**Key design constraint:** Hermes allows exactly one external memory provider.
This plugin IS that one provider — it delegates to N backends internally. All
thread safety, runtime management, and provider coordination is the plugin's
responsibility, not upstream's. Zero upstream proposals needed.

## Quick reference

```bash
# Test
PYTHONPATH=src python3 -m pytest tests/ -v

# Lint
ruff check src/ tests/
ruff format --check src/ tests/

# Coverage
PYTHONPATH=src python3 -m pytest tests/ --cov=multi_memory --cov-report=term-missing
```

All tests run without real backends — everything is mocked. The
`@requires_holographic` skip marker is used for tests that need the Hermes
`plugins` package (CI doesn't have it).

## Architecture

```
MultiMemoryProvider (implements MemoryProvider ABC)
├── _MnemosyneAdapter     → loads via plugins.memory plugin loader
├── _Mem0Adapter          → loads via _try_import("plugins.memory.mem0")
├── _HolographicAdapter   → loads via _try_import("plugins.memory.holographic")
├── _HonchoAdapter        → loads via _try_import("plugins.memory.honcho")
├── _OpenVikingAdapter    → loads via _try_import("plugins.memory.openviking")
├── _HindsightAdapter     → loads via _try_import("plugins.memory.hindsight")
├── _RetainDBAdapter      → loads via _try_import("plugins.memory.retaindb")
├── _ByteRoverAdapter     → loads via _try_import("plugins.memory.byterover")
├── _SupermemoryAdapter   → loads via _try_import("plugins.memory.supermemory")
└── _GenericAdapter       → auto-discovered via load_memory_provider() (not in _SUB_CLASSES)
```

Each adapter inherits from `_SubProviderAdapter` which handles:
- Importing the real provider class via `_try_import()` (safe, returns None on failure)
- Delegating all lifecycle methods to the real provider
- Prefix routing for tool names via `_renorm_schemas()` (shared DRY helper)
- Cached introspection: `_metadata_write_mode()` and `_sync_accepts_messages()`
  computed once per adapter lifetime
- `close()` → `shutdown()` fallback for proper cleanup

### Custom backends (`_GenericAdapter`)

Any `MemoryProvider` implementation dropped into `plugins/memory/<name>/` is
auto-discovered via Hermes's `load_memory_provider()`. No adapter needed —
the `_GenericAdapter` wraps it and passes tool names through unchanged
(no prefix added; the provider handles its own naming).

### Prefix handling

All hardcoded backends self-prefix their tools. The adapter pattern uses
`_renorm_schemas()`:
1. Strip existing prefix from all tool names
2. Re-add it (ensures exactly one prefix)
3. `handle_tool_call()`: pass through full prefixed name to delegate

`MultiMemoryProvider.handle_tool_call()` matches tools by adapter PREFIX
(not `sub.name`) to handle ByteRover and OpenViking correctly.

### Mnemosyne is special

It's a user-installed plugin (not a pip package), so `_MnemosyneAdapter.__init__`
uses `plugins.memory.load_memory_provider()` with a fallback to `_try_import()`.

### ByteRover and OpenViking have different config keys and tool prefixes

- ByteRover: CONFIG_KEY=`byterover`, PREFIX=`brv` (tools are `brv_query`, etc.)
- OpenViking: CONFIG_KEY=`openviking`, PREFIX=`viking` (tools are `viking_search`, etc.)

## Thread safety

`MultiMemoryProvider._lock` (RLock) protects:
- `_subs` list mutations (add/remove provider)
- `_snapshot()` — copies `_subs` before dispatching to prevent mid-iteration mutation
- `shutdown()` — clears `_subs` to prevent post-shutdown calls to dead delegates
- `initialize()` — records failures for status reporting

Pattern: snapshot under lock, dispatch outside lock. This prevents deadlock
when a lifecycle callback triggers another method.

## Runtime management

```python
# Add a backend at runtime
provider.add_provider(mem0_adapter)

# Remove a backend (shuts it down via _batch_shutdown)
provider.remove_provider("mem0")

# Lookup
sub = provider.get_provider("mem0")
names = provider.providers  # property: list of active sub-provider names
```

## CLI commands

Registered via `cli.py`'s `register_cli()` function, discovered by
Hermes's `discover_plugin_cli_commands()`.

```bash
hermes multi setup            # interactive curses-based setup wizard
hermes multi setup <name>     # configure a specific backend interactively
hermes multi status           # active backends + health + plugin status
hermes multi list             # all backends, active markers
hermes multi add <name>       # add a backend to config
hermes multi remove <name>    # remove a backend from config
```

The setup wizard walks through per-backend configuration fields (API keys,
model choices, endpoint URLs) using a curses-based picker with terminal
fallback. It auto-installs Python dependencies from each backend's
`plugin.yaml` and writes secrets to `~/.hermes/.env` with 0600 permissions.

`ALL_BACKENDS` in `cli.py` lists all 9 hardcoded backends. Custom backends
(via `_GenericAdapter`) are discovered at runtime but not listed in CLI help.

## Error logging standard

Every `except` block in the plugin MUST:
1. Capture the exception with `as exc`
2. Log it with `logger.debug` or `logger.warning`
3. Log the error (the backend stays in the list — no exclusion)

Zero tolerance for silent failures:
- `except: pass` → forbidden
- `except Exception:` without `as exc` → forbidden
- Bare `except:` → forbidden

**Config-time** failures (missing package, missing credentials) use
`logger.warning` so users see them at default log levels.
**Runtime lifecycle** failures use `logger.debug` since they're transient.

## Method signatures

The plugin MUST match the Hermes `MemoryProvider` ABC signatures exactly.
Check the ABC at:

```
hermes-agent/agent/memory_provider.py
```

## Testing patterns

### Mocking backends that use `plugins.memory`

```python
import sys

mock_pm = mock.MagicMock()
mock_pm.load_memory_provider.return_value = mock_delegate
old = sys.modules.get("plugins.memory")
sys.modules["plugins.memory"] = mock_pm
try:
    adapter = _MnemosyneAdapter()
finally:
    if old is not None:
        sys.modules["plugins.memory"] = old
    else:
        sys.modules.pop("plugins.memory", None)
```

### Mocking `plugins.memory.<name>` for hardcoded backends

```python
mock_mod = mock.MagicMock()
mock_mod.SomeProvider.return_value = mock_delegate
sys.modules["plugins.memory.some_backend"] = mock_mod
```

CI doesn't have the `plugins` package, so `_try_import()` returns None
and adapters gracefully skip. Use `@requires_holographic` for tests that
need the full plugin loader.

### Exception isolation tests

```python
# Good
sub.method.side_effect = RuntimeError("fail")

# Bad — fragile and hard to read
sub.method = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("fail"))
```



## Key files

| File | Purpose |
|------|---------|
| `src/multi_memory/__init__.py` | `register()` entry point, `MultiMemoryProvider`, `_snapshot()`, `_batch_shutdown()`, `_fan_out()`, `_try_generic_backend()`, `__repr__`, `get_status_config()` |
| `src/multi_memory/_version.py` | `__version__` — single source of truth |
| `src/multi_memory/adapters.py` | `_SubProviderAdapter` base + `_renorm_schemas()` + `_normalize_tool_schema()` + cached introspection + 9 hardcoded adapters + `_GenericAdapter` |
| `src/multi_memory/budget.py` | `ToolBudgetWarning` — warns when schema count exceeds threshold |
| `src/multi_memory/cli.py` | `register_cli()` + `hermes multi {setup,status,list,add,remove,update,validate}` + `create_adapter()` + `BACKEND_CATEGORIES` + interactive curses wizard + dependency installer + env var manager + `ALL_BACKENDS` |
| `src/multi_memory/config.py` | `_is_disabled()`, `_normalize_multi_config()`, `load_full_config()`, `load_multi_config()`, `get_enabled_backends()`, `MNEMOSYNE_PLUGIN_DIRS` |
| `src/multi_memory/discovery.py` | `discover_backends()`, `installed_backends()` |

| `src/multi_memory/validate.py` | `NamespaceValidator` — checks adapter PREFIX attributes |
| `src/multi_memory/plugin.yaml` | Hermes plugin metadata (name: `multi`) |
| `tests/test_adapters.py` | Adapter tests, provider tests, lifecycle hook tests |
| `tests/test_adapters_extra.py` | Introspection, fan-out, config error path tests |
| `tests/test_api_parity.py` | ABC parity: backup_paths, rewound, JSON contract, batch shutdown |
| `tests/test_audit_coverage.py` | Error paths: schema validation, _fan_out, inspect.signature, discovery |
| `tests/test_budget.py` | ToolBudgetWarning + NamespaceValidator tests |
| `tests/test_cli.py` | CLI subcommand tests |
| `tests/test_config.py` | Config loading, format precedence, error paths |
| `tests/test_config_robustness.py` | `_is_disabled` semantics (bool/int/float/string/off/disabled), `_normalize_multi_config` non-dict guards, unhashable providers, `load_full_config` edge cases |
| `tests/test_discovery.py` | Backend discovery + installation detection tests |
| `tests/test_adapter_robustness.py` | Adapter close/config_schema lifecycle, schema cache thread safety, re-entrancy guard, prefix routing, `_renorm_schemas` missing name |
| `tests/test_cli_robustness.py` | CLI dispatch, `_cmd_add/remove/status/update` edge cases, `get_enabled_backends` guards, `_set_active_backends` coercion, `get_status_config` guards, `_install_dependencies` guards |
| `tests/test_generic_adapter.py` | `_GenericAdapter` + `_try_generic_backend()` tests |
| `tests/test_cli_validate.py` | `create_adapter()` + `_cmd_validate` tests |
| `tests/test_cli_fifth_pass.py` | `--check`, `--force`, `--all`, `--config-only` flag tests, categorized list, dispatch routing |
| `tests/test_cli_pass13.py` | `_print_legacy_provider_config` early return + else branch, `_cmd_list` non-dict memory config |

| `.github/workflows/ci.yml` | CI — Python 3.10/3.11/3.12/3.13/3.14, `astral-sh/ruff-action`, actions v6, pytest + 95% coverage, mypy, hermes-agent pinned to `v2026.7.7.2` |

## Module dependency graph

```
_version.py  (no internal deps — single source of __version__)
config.py    (no internal deps — canonical foundation layer)
  ↓
adapters.py  (imports MNEMOSYNE_PLUGIN_DIRS from config)
  ↓
__init__.py  (imports _normalize_multi_config, _is_disabled from config; adapters)
  ↓
discovery.py (imports MNEMOSYNE_PLUGIN_DIRS, _get_hermes_home from config)
  ↓
cli.py       (imports __version__ from _version; get_enabled_backends from config)
```

No cycles. `config.py` and `_version.py` are leaf modules — every other
module depends on them, never the reverse.

## Custom backend compatibility

The plugin mirrors upstream Hermes MemoryManager improvements:

- **`_normalize_tool_schema()`** in `adapters.py` mirrors
  `agent.memory_manager.normalize_tool_schema` — custom backends that
  return double-wrapped OpenAI tool schemas
  (`{"type": "function", "function": {...}}`) are unwrapped transparently.
- **All lifecycle methods forward `**kwargs`** — `sync_turn`, `prefetch`,
  `queue_prefetch`, `on_turn_start`, `on_session_switch`, `on_delegation`
  all pass through extra kwargs to the delegate. This ensures future ABC
  additions are forwarded without adapter changes.
- **`get_enabled_backends()`** in `config.py` replaces the deleted
  `_get_active_backends()` from `cli.py` — single canonical config parser.

## Config precedence

`get_enabled_backends()` reads config in this order:
1. `memory.multi.backends` dict (verbose, per-backend options)
2. `memory.providers` list (concise)
3. `memory.provider` string (single-provider legacy)

First match wins. A backend value of `false`, `"false"`, `"False"`, `"FALSE"`,
`"0"`, `"0.0"`, `"no"`, `"NO"`, `"off"`, `"OFF"`, `"disabled"`, `"DISABLED"`,
`0`, `0.0`, or `null` disables it (case-insensitive string matching).

## Gotchas

1. **Standalone vs Hermes** — The plugin works both inside Hermes (real imports)
   and standalone (fallback stubs). Don't add hard imports from `tools.registry`
   or `agent.memory_provider` — use `try/except ImportError`.

2. **`find_spec` raises for missing parent packages** —
   `find_spec("plugins.memory.holographic")` raises `ModuleNotFoundError` when
   `plugins` doesn't exist. Always wrap in `try/except (ModuleNotFoundError, ValueError)`.

3. **Config has two formats** — `providers: [list]` and `multi.backends: {dict}`
   are both valid. The `multi.backends` dict wins when both are present.
   Tests must cover both.

4. **One external provider limit** — Hermes deliberately limits to one external
   memory provider. This plugin IS that one provider. Do NOT propose lifting
   the limit upstream — it's been rejected 5+ times. All multi-provider
   coordination is the plugin's job.

5. **`shutdown()` clears `_subs`** — After shutdown, the provider is inert.
   Don't call lifecycle methods after shutdown. `initialize()` must be called
   again to re-populate.

6. **`_GenericAdapter` passes tool names through** — Unlike hardcoded adapters,
   the generic adapter doesn't add a prefix. The custom backend handles its
   own naming.

7. **Plugin name is `multi`** — In `plugin.yaml` and config, the name is `multi`
   (not `multi-memory`). Matches Hermes discovery convention where config key
   = plugin directory name.

8. **Install via `hermes plugins install`** —
   `hermes plugins install someaka/multi-memory-plugin`. Then set the provider
   and add backends:
   ```bash
   hermes plugins install someaka/multi-memory-plugin
   hermes config set memory.provider multi
   hermes multi setup            # interactive wizard — picks backends + configures them
   ```
   For development, use `--force` to reinstall:
   ```bash
   hermes plugins install --force someaka/multi-memory-plugin
   ```
