# AGENT.md

Instructions for AI coding assistants working on the multi-memory plugin.

## Overview

This is a standalone Hermes Agent plugin that runs multiple memory backends simultaneously. It lives in `src/multi_memory/` and is installed into Hermes at `~/.hermes/hermes-agent/plugins/memory/multi/`.

The plugin implements the `MemoryProvider` ABC from `agent.memory_provider` in the Hermes core. It fans lifecycle calls across active sub-providers with per-provider error isolation.

## Quick reference

```bash
# Test
python -m pytest tests/ -v

# Lint
ruff check src/ tests/

# Coverage
python -m pytest tests/ --cov=src/multi_memory --cov-report=term-missing
```

All tests run without real backends — everything is mocked. The `@requires_holographic` skip marker is used for tests that need the Hermes `plugins` package (CI doesn't have it).

## Architecture

```
MultiMemoryProvider (implements MemoryProvider ABC)
├── _MnemosyneAdapter    → loads via plugins.memory plugin loader
├── _Mem0Adapter         → loads via _try_import("plugins.memory.mem0")
├── _HolographicAdapter  → loads via _try_import("plugins.memory.holographic")
└── _HonchoAdapter       → loads via _try_import("plugins.memory.honcho")
```

Each adapter inherits from `_SubProviderAdapter` which handles:
- Importing the real provider class via `_try_import()` (safe, returns None on failure)
- Delegating all lifecycle methods to the real provider
- Prefix routing for tool names

**Mnemosyne is special** — it's a user-installed plugin (not a pip package), so `_MnemosyneAdapter.__init__` uses `plugins.memory.load_memory_provider()` with a fallback to `_try_import()`.

## Method signatures

The plugin MUST match the Hermes `MemoryProvider` ABC signatures exactly. When adding or modifying lifecycle methods, check the ABC at:

```
hermes-agent/agent/memory_provider.py
```

Current ABC signatures:

```python
def on_turn_start(self, turn_number: int, message: str, **kwargs) -> None
def on_session_end(self, messages: List[Dict[str, Any]]) -> None
def on_session_switch(self, new_session_id: str, *, parent_session_id: str = "", reset: bool = False, **kwargs) -> None
def on_memory_write(self, action: str, target: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> None
def on_delegation(self, task: str, result: str, *, child_session_id: str = "", **kwargs) -> None
def on_pre_compress(self, messages: List[Dict[str, Any]]) -> str
```

## Testing patterns

### Mocking backends that use `plugins.memory`

The `plugins.memory` package doesn't exist in standalone CI. Tests that need it must inject a mock into `sys.modules`:

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

### Testing with mock providers

The `provider` fixture in `test_adapters.py` creates a `MultiMemoryProvider` with mock sub-providers:

```python
@pytest.fixture
def provider():
    p = MultiMemoryProvider()
    mock_holo = mock.MagicMock()
    mock_holo.name = "holographic"
    mock_holo.get_tool_schemas.return_value = [...]
    p._subs = [mock_holo, mock_memo]
    return p
```

### Exception isolation tests

Use `side_effect` on mocks — don't use the fragile generator-throw pattern:

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
| `src/multi_memory/adapters.py` | `_SubProviderAdapter` base + 4 concrete adapters |
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

3. **Adapter prefix handling varies** — Mnemosyne tools are self-prefixed (pass through). Mem0/Honcho tools are self-prefixed (strip+re-add). Holographic tools are unprefixed (base class adds). Check the adapter before changing prefix logic.

4. **Config has two formats** — `providers: [list]` and `multi.backends: {dict}` are both valid. The `providers` list wins. Tests must cover both.
