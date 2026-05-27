# Multi-Memory Plugin — Hermes Agent

Run multiple memory providers (Mnemosyne, Mem0, Holographic, Honcho) simultaneously via a single `MemoryProvider` instance.

## Install

Copy the plugin into Hermes's plugin directory:

```bash
cp -r src/multi_memory ~/.hermes/hermes-agent/plugins/memory/multi/
# or symlink:
ln -sf $(pwd)/src/multi_memory ~/.hermes/hermes-agent/plugins/memory/multi/
```

## Configuration

Either format works:

```yaml
# ~/.hermes/config.yaml
memory:
  provider: multi
  multi:
    backends:
      mnemosyne: {}              # stdlib-only; no pip install needed
      mem0: {}                   # requires MEM0_API_KEY in env
      holographic: {}            # stdlib-only
      honcho: {}                 # requires honcho-ai package
```

Or the INVESTIGATION-C canonical format:

```yaml
memory:
  provider: multi
  providers:
    - "mnemosyne"
    - "mem0"
    - "holographic"
    - "honcho"
```

## Per-backend dependencies

| Backend | pip install | Env vars required |
|---------|------------|-------------------|
| Mnemosyne | [plugin](https://github.com/AxDSan/mnemosyne) | None |
| Mem0 | `mem0ai>=0.1` | `MEM0_API_KEY` |
| Holographic | stdlib-only | None |
| Honcho | `honcho-ai` | `HONCHO_API_KEY`, `HONCHO_APP_ID` |

**Notes:**
- Mnemosyne is a user-installed plugin (deployed to `~/.hermes/plugins/mnemosyne/`).
  The adapter uses the Hermes plugin loader to find it.
- Mem0 and Honcho tools are self-prefixed by their providers — the adapter
  strips and re-adds the prefix to avoid double-prefixing (`mem0_mem0_search`).
- If a backend is not installed, the adapter raises at init time and the loader
  in `_load_backends_from_config` catches the error and skips it — no crash,
  just a debug log.

## How it works

```
Hermes core → MemoryManager._tool_to_provider["mnemosyne_recall"]
           → MultiMemoryProvider.handle_tool_call("mnemosyne_recall", args)
           → prefix match: "mnemosyne_" → routes to _MnemosyneAdapter
           → _MnemosyneAdapter.handle_tool_call("mnemosyne_recall", args)
           → real mnemosyne MemoryProvider.handle_tool_call("mnemosyne_recall", args)
```

Each adapter handles prefix differently based on how the real provider names its tools:
- **Mnemosyne**: tools are self-prefixed (`mnemosyne_recall`) — adapter passes through
- **Mem0 / Honcho**: tools are self-prefixed (`mem0_search`) — adapter strips+re-adds
- **Holographic**: tools are unprefixed (`fact_store`) — base class adds prefix

All lifecycle hooks (`initialize`, `prefetch`, `sync_turn`, `shutdown`, etc.) fan out
to every active sub-provider with per-provider error isolation (`try/except`).

## Acceptance criteria

- [x] `plugin.yaml`, `README.md`, `__init__.py`, `adapters.py` exist
- [x] `MultiMemoryProvider` passes `isinstance(p, MemoryProvider)` = True
- [x] 0 tool name collisions in `get_tool_schemas()` (first-seen wins)
- [x] `handle_tool_call()` routes to correct sub-provider by prefix
- [x] `initialize()` / `shutdown()` propagate to all active sub-providers
- [x] Unit tests pass (`python -m pytest tests/ -v`)

## File structure

```
multi-memory-plugin/
├── plugin.yaml                  → Hermes plugin metadata
├── pyproject.toml               → Build config
├── setup.cfg                    → flake8 + pytest config
├── Makefile                     → install, test, lint, coverage targets
├── README.md                    → This file
├── CONFIG.md                    → Full configuration reference
├── CHANGELOG.md                 → Version history
├── src/
│   └── multi_memory/
│       ├── __init__.py          → register() + MultiMemoryProvider
│       ├── adapters.py          → 4 sub-provider adapters
│       ├── budget.py            → ToolBudgetWarning (schema count monitor)
│       ├── config.py            → Config loader helpers
│       ├── discovery.py         → Backend discovery + install detection
│       ├── health.py            → HealthTracker + circuit breaker
│       └── validate.py          → NamespaceValidator (PREFIX checks)
├── tests/
│   ├── conftest.py              → Shared fixtures + markers
│   ├── test_adapters.py         → Adapters, provider, lifecycle hooks
│   ├── test_budget.py           → Budget + namespace validator
│   ├── test_config.py           → Config loading + normalization
│   ├── test_discovery.py        → Backend discovery
│   └── test_health.py           → HealthTracker + timeout_wrapper
└── scripts/
    ├── health_check.py          → CLI health check (--json, --verbose)
    ├── install.sh               → One-command installer (symlink + validate)
    └── setup.sh                 → Interactive setup wizard
```