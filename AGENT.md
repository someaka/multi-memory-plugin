# AGENT.md

Instructions for AI coding assistants working on the multi-memory plugin.

## Overview

This is a standalone Hermes Agent plugin that runs multiple memory backends
simultaneously. It lives in `src/multi_memory/` and is installed into Hermes
at `~/.hermes/hermes-agent/plugins/memory/multi/`.

The plugin implements the `MemoryProvider` ABC from `agent.memory_provider` in
the Hermes core. It fans lifecycle calls across active sub-providers with
per-provider error isolation, circuit-breaker protection (HealthTracker), and
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
├── _GenericAdapter       → auto-discovered via load_memory_provider()
└── _SupermemoryAdapter   → loads via _try_import("plugins.memory.supermemory")
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

## HealthTracker (circuit breaker)

`health.py` implements a half-open circuit breaker with exponential backoff:

1. **Closed** (normal): requests pass through. Failures increment counter.
2. **Open** (tripped): after 3 consecutive failures, the backend is skipped.
   Cooldown starts at 30s.
3. **Half-open** (probe): after cooldown expires, one probe call goes through.
   - Success → circuit closes, backoff resets to 30s.
   - Failure → circuit re-opens, cooldown doubles (30→60→120→300s cap).

`HealthTracker` has its own `threading.Lock` — independent of
`MultiMemoryProvider._lock` since health mutations happen during dispatch.

Key methods:
- `is_open(name)` → bool: should we skip this backend?
- `record_success(name)`: close circuit, reset backoff
- `record_failure(name)`: increment failures, potentially open circuit
- `remaining_cooldown(name)` → float: seconds until next probe allowed

## Thread safety

`MultiMemoryProvider._lock` (RLock) protects:
- `_subs` list mutations (add/remove provider)
- `_snapshot()` — copies `_subs` before dispatching to prevent mid-iteration mutation
- `shutdown()` — clears `_subs` to prevent post-shutdown calls to dead delegates
- `initialize()` — checks circuit breaker before attempting init

Pattern: snapshot under lock, dispatch outside lock. This prevents deadlock
when a lifecycle callback triggers another method.

## Runtime management

```python
# Add a backend at runtime
provider.add_provider("mem0", mem0_instance)

# Remove a backend (shuts it down, resets health, cleans up tools)
provider.remove_provider("mem0")

# Lookup
sub = provider.get_provider("mem0")
names = provider.providers  # property: list of active sub-provider names
```

## CLI commands

Registered via `cli.py`'s `register_cli()` function, discovered by
Hermes's `discover_plugin_cli_commands()`.

```bash
hermes multi status          # active backends + config format
hermes multi list            # all backends, active markers
hermes multi add <name>      # add a backend to config
hermes multi remove <name>   # remove a backend from config
```

`ALL_BACKENDS` in `cli.py` lists all 9 hardcoded backends. Custom backends
(via `_GenericAdapter`) are discovered at runtime but not listed in CLI help.

## Error logging standard

Every `except` block in the plugin MUST:
1. Capture the exception with `as exc`
2. Log it with `logger.debug` or `logger.warning`
3. Record failure with `self._health.record_failure(sub.name)` (for lifecycle hooks)

Zero tolerance for silent failures:
- `except: pass` → forbidden
- `except Exception:` without `as exc` → forbidden
- Bare `except:` → forbidden

**Config-time** failures (missing package, missing credentials) use
`logger.warning` so users see them at default log levels.
**Runtime lifecycle** failures use `logger.debug` since they're transient
and the circuit breaker handles them.

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

### Half-open circuit breaker tests

```python
# Force circuit open
for _ in range(3):
    tracker.record_failure("test")
assert tracker.is_open("test")

# Advance past cooldown
tracker._last_failure["test"] = time.time() - 31
assert not tracker.is_open("test")  # half-open: allows probe
```

## Key files

| File | Purpose |
|------|---------|
| `src/multi_memory/__init__.py` | `register()` entry point, `MultiMemoryProvider` (568 lines), `_snapshot()`, `_close_or_shutdown()`, `_is_disabled()`, `_fan_out()`, `_try_generic_backend()`, `__repr__` |
| `src/multi_memory/adapters.py` | `_SubProviderAdapter` base + `_renorm_schemas()` + cached introspection + 9 hardcoded adapters + `_GenericAdapter` (396 lines) |
| `src/multi_memory/budget.py` | `ToolBudgetWarning` — warns when schema count exceeds threshold |
| `src/multi_memory/cli.py` | `register_cli()` + `hermes multi {status,list,add,remove}` + `ALL_BACKENDS` |
| `src/multi_memory/config.py` | `load_multi_config()`, `get_enabled_backends()` with lazy paths |
| `src/multi_memory/discovery.py` | `discover_backends()`, `installed_backends()` |
| `src/multi_memory/health.py` | `HealthTracker` — half-open circuit breaker with exponential backoff, `timeout_wrapper` |
| `src/multi_memory/validate.py` | `NamespaceValidator` — checks adapter PREFIX attributes |
| `src/multi_memory/plugin.yaml` | Hermes plugin metadata (name: `multi`) |
| `tests/test_adapters.py` | Adapter tests, provider tests, lifecycle hook tests |
| `tests/test_cli.py` | CLI subcommand tests |
| `tests/test_generic_adapter.py` | `_GenericAdapter` + `_try_generic_backend()` tests |
| `tests/test_health.py` | Half-open recovery, thread safety, exponential backoff |
| `.github/workflows/ci.yml` | CI — Python 3.11/3.12/3.13, ruff + pytest + 90% coverage |

## Config precedence

`get_enabled_backends()` reads config in this order:
1. `memory.multi.backends` dict (verbose, per-backend options)
2. `memory.providers` list (concise)
3. `memory.provider` string (single-provider legacy)

First match wins. A backend value of `false`, `"false"`, `"0"`, `0`,
or `null` disables it.

## Gotchas

1. **Standalone vs Hermes** — The plugin works both inside Hermes (real imports)
   and standalone (fallback stubs). Don't add hard imports from `tools.registry`
   or `agent.memory_provider` — use `try/except ImportError`.

2. **`find_spec` raises for missing parent packages** —
   `find_spec("plugins.memory.holographic")` raises `ModuleNotFoundError` when
   `plugins` doesn't exist. Always wrap in `try/except (ModuleNotFoundError, ValueError)`.

3. **Config has two formats** — `providers: [list]` and `multi.backends: {dict}`
   are both valid. The `providers` list wins. Tests must cover both.

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
   `hermes plugins install someaka/multi-memory-plugin`. Not a symlink.
   For development, two symlinks are required:
   ```bash
   hermes plugins install --force someaka/multi-memory-plugin
   hermes config set memory.provider multi
   ```
