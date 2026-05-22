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
| Mnemosyne | stdlib-only | None |
| Mem0 | `mem0ai>=0.1` | `MEM0_API_KEY` |
| Holographic | stdlib-only | None |
| Honcho | `honcho-ai` | `HONCHO_API_KEY`, `HONCHO_APP_ID` |

**Note:** If a backend is not installed, the adapter raises at init time and the loader in `_load_backends_from_config` catches the error and skips it — no crash, just a debug log.

## How it works

```
Hermes core → MemoryManager._tool_to_provider["mnemosyne_recall"]
           → MultiMemoryProvider.handle_tool_call("mnemosyne_recall", args)
           → strips "mnemosyne_" → inner = "recall"
           → _MnemosyneAdapter.handle_tool_call("recall", args)
           → real mnemosyne MemoryProvider.handle_tool_call("recall", args)
```

All lifecycle hooks (`initialize`, `prefetch`, `sync_turn`, `shutdown`, etc.) fan out
to every active sub-provider with per-provider error isolation (`try/except`).

## Acceptance criteria

- [x] `plugin.yaml`, `README.md`, `__init__.py`, `adapters.py` exist
- [ ] `MultiMemoryProvider` passes `isinstance(p, MemoryProvider)` = True
- [ ] 0 tool name collisions in `get_tool_schemas()` (first-seen wins)
- [ ] `handle_tool_call()` routes to correct sub-provider by prefix
- [ ] `initialize()` / `shutdown()` propagate to all active sub-providers
- [ ] Unit tests pass (`python -m pytest tests/ -v`)

## File structure

```
multi-memory-plugin/
├── plugin.yaml                  → Hermes plugin metadata
├── pyproject.toml               → Build config
├── README.md                    → This file
├── src/
│   └── multi_memory/
│       ├── __init__.py          → register() + MultiMemoryProvider
│       ├── adapters.py          → Protocol + 4 sub-provider adapters
│       └── config.py            → Config loader helper
└── tests/
    └── test_adapters.py         → Unit tests (schema prefix, dedup, routing)
```
