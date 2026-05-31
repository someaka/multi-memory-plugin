# Contributing

## Setup

```bash
git clone https://github.com/someaka/multi-memory-plugin.git
cd multi-memory-plugin
pip install -e ".[all,test]"
```

## Run tests

```bash
python -m pytest tests/ -v
```

## Lint

```bash
ruff check src/ tests/
ruff check src/ tests/ --fix   # auto-fix
```

## Adding a new backend

1. Create `src/multi_memory/adapters.py` — add a `_YourAdapter` class:

```python
class _YourAdapter(_SubProviderAdapter):
    CONFIG_KEY = "your_backend"     # config.yaml key
    MODULE     = "plugins.memory.your_backend"  # import path
    CLASS      = "YourBackendMemoryProvider"     # class name
    PREFIX     = "your"             # tool name prefix

    def get_tool_schemas(self) -> list[dict]:
        raw = self._delegate.get_tool_schemas()
        return _renorm_schemas(raw, self.PREFIX)

    def handle_tool_call(self, tool_name: str, args: dict, **kwargs: Any) -> str:
        return self._delegate.handle_tool_call(tool_name, args, **kwargs)
```

2. Add to `_SUB_CLASSES` in `__init__.py`
3. Add to `ALL_BACKENDS` in `cli.py`
4. Add tests in `tests/test_adapters.py`
5. Add entry to `CONFIG.md`

The `PREFIX` is what routes tool calls. If your backend self-prefixes
its tools (e.g. `your_search`), the strip+re-add in `_renorm_schemas`
handles it. If it doesn't (e.g. `search`), the prefix is added.

## Custom backends (no code changes)

Any `MemoryProvider` implementation dropped into `plugins/memory/<name>/`
is auto-discovered via Hermes's plugin loader. No adapter needed — just
add the name to config and the `_GenericAdapter` wraps it.

## Architecture

```
MultiMemoryProvider (MemoryProvider ABC)
├── _MnemosyneAdapter     → plugins.memory plugin loader
├── _Mem0Adapter          → plugins.memory.mem0
├── _HolographicAdapter   → plugins.memory.holographic
├── _HonchoAdapter        → plugins.memory.honcho
├── _OpenVikingAdapter    → plugins.memory.openviking
├── _HindsightAdapter     → plugins.memory.hindsight
├── _RetainDBAdapter      → plugins.memory.retaindb
├── _ByteRoverAdapter     → plugins.memory.byterover
├── _SupermemoryAdapter   → plugins.memory.supermemory
└── _GenericAdapter       → any custom backend via plugin discovery
```

Each adapter wraps a real `MemoryProvider` and handles:
- Prefix routing (strip+re-add via `_renorm_schemas`)
- Introspection-aware dispatch (`_metadata_write_mode`, `_sync_accepts_messages`)
- Close/shutdown cleanup

`MultiMemoryProvider` handles:
- Thread-safe snapshot dispatch (`_snapshot()`)
- Circuit breaker per backend (`HealthTracker`)
- Schema validation before registration
- Runtime add/remove of backends
- Lifecycle fanout (all hooks fire on all active backends)

## Error handling standard

Every `except` block must:
1. Capture the exception with `as exc`
2. Log it with `logger.warning`
3. Record failure with `self._health.record_failure(sub.name)` (for lifecycle hooks)

Zero tolerance for silent failures.

## CI

Runs on push to `main` and on PRs. Python 3.11, 3.12, 3.13.
Ruff lint + pytest with 90% coverage threshold.
