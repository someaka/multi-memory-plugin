# AGENT.md

Instructions for AI coding assistants working on the multi-memory plugin.

## Overview

This is a standalone Hermes Agent plugin that runs multiple memory backends simultaneously. It lives in `src/multi_memory/` and is installed into Hermes at `~/.hermes/hermes-agent/plugins/memory/multi/`.

The plugin implements the `MemoryProvider` ABC from `agent.memory_provider` in the Hermes core. It fans lifecycle calls across active sub-providers with per-provider error isolation and circuit-breaker protection (HealthTracker).

## Quick reference

```bash
# Test
PYTHONPATH=src python3 -m pytest tests/ -v

# Lint
ruff check src/ tests/

# Coverage
PYTHONPATH=src python3 -m pytest tests/ --cov=multi_memory --cov-report=term-missing
```

All tests run without real backends — everything is mocked. The `@requires_holographic` skip marker is used for tests that need the Hermes `plugins` package (CI doesn't have it).

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
└── _SupermemoryAdapter   → loads via _try_import("plugins.memory.supermemory")
```

Each adapter inherits from `_SubProviderAdapter` which handles:
- Importing the real provider class via `_try_import()` (safe, returns None on failure)
- Delegating all lifecycle methods to the real provider
- Prefix routing for tool names

**Mnemosyne is special** — it's a user-installed plugin (not a pip package), so `_MnemosyneAdapter.__init__` uses `plugins.memory.load_memory_provider()` with a fallback to `_try_import()`.

**ByteRover and OpenViking have different config keys and tool prefixes:**
- ByteRover: CONFIG_KEY=`byterover`, PREFIX=`brv` (tools are `brv_query`, etc.)
- OpenViking: CONFIG_KEY=`openviking`, PREFIX=`viking` (tools are `viking_search`, etc.)

## Prefix handling

All 9 backends self-prefix their tools. The adapter pattern is:
1. `get_tool_schemas()`: strip existing prefix, re-add it (ensures exactly one prefix)
2. `handle_tool_call()`: pass through full prefixed name to delegate

`MultiMemoryProvider.handle_tool_call()` matches tools by adapter PREFIX (not `sub.name`) to handle ByteRover and OpenViking correctly.

## HealthTracker integration

All lifecycle methods check `self._health.is_open(sub.name)` before calling sub-providers. On success, `record_success()` resets the failure counter. On failure, `record_failure()` increments it. After 3 consecutive failures, the circuit opens and that backend is skipped.

## Method signatures

The plugin MUST match the Hermes `MemoryProvider` ABC signatures exactly. Check the ABC at:

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
| `src/multi_memory/__init__.py` | `register()` entry point, `MultiMemoryProvider`, config normalization |
| `src/multi_memory/adapters.py` | `_SubProviderAdapter` base + 9 concrete adapters |
| `src/multi_memory/budget.py` | `ToolBudgetWarning` — warns when schema count exceeds threshold |
| `src/multi_memory/config.py` | `load_multi_config()`, `get_enabled_backends()` |
| `src/multi_memory/discovery.py` | `discover_backends()`, `installed_backends()` |
| `src/multi_memory/health.py` | `HealthTracker` (circuit breaker), `timeout_wrapper` |
| `src/multi_memory/validate.py` | `NamespaceValidator` — checks adapter PREFIX attributes |
| `tests/conftest.py` | Shared fixtures, `requires_holographic` marker |
| `tests/test_adapters.py` | Adapter tests, provider tests, lifecycle hook tests |
| `.github/workflows/ci.yml` | CI — Python 3.11/3.12/3.13, ruff + pytest + coverage |

## Gotchas

1. **Standalone vs Hermes** — The plugin works both inside Hermes (real imports) and standalone (fallback stubs). Don't add hard imports from `tools.registry` or `agent.memory_provider` — use `try/except ImportError`.

2. **`find_spec` raises for missing parent packages** — `find_spec("plugins.memory.holographic")` raises `ModuleNotFoundError` when `plugins` doesn't exist. Always wrap in `try/except (ModuleNotFoundError, ValueError)`.

3. **Adapter prefix handling varies** — All 9 backends self-prefix their tools. The adapter strips and re-adds the prefix. ByteRover uses `brv_` and OpenViking uses `viking_` as tool prefixes (differing from their config keys).

4. **Config has two formats** — `providers: [list]` and `multi.backends: {dict}` are both valid. The `providers` list wins. Tests must cover both.
