# multi-memory

> Run multiple [Hermes](https://github.com/NousResearch/hermes-agent) memory backends simultaneously through a single provider.

[![CI](https://github.com/someaka/multi-memory-plugin/actions/workflows/ci.yml/badge.svg)](https://github.com/someaka/multi-memory-plugin/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: AGPL v3](https://img.shields.io/badge/license-AGPL%20v3-blue.svg)](LICENSE)

---

## What it does

Hermes supports one memory provider at a time. This plugin lets you run **all of them at once** — Mnemosyne for local recall, Mem0 for semantic search, Holographic for vector embeddings, Honcho for hosted memory — without choosing just one.

Tool calls route to the right backend automatically. Lifecycle hooks fan out to every active provider. Failures in one backend don't take down the others.

## Quick start

**1. Install** — copy or symlink into Hermes:

```bash
# Option A: copy
cp -r src/multi_memory ~/.hermes/hermes-agent/plugins/memory/multi/

# Option B: symlink (stays in sync with the repo)
ln -sf "$(pwd)/src/multi_memory" ~/.hermes/hermes-agent/plugins/memory/multi/
```

**2. Configure** — add to `~/.hermes/config.yaml`:

```yaml
memory:
  provider: multi
  multi:
    backends:
      mnemosyne: {}
      holographic: {}
      # mem0: {}       # uncomment if you have MEM0_API_KEY
      # honcho: {}     # uncomment if you have honcho-ai installed
```

**3. Restart** Hermes. That's it.

## Backends

| Backend | Setup | Env vars |
|---------|-------|----------|
| **Mnemosyne** | Install the [mnemosyne plugin](https://github.com/AxDSan/mnemosyne) to `~/.hermes/plugins/mnemosyne/` | — |
| **Holographic** | None — stdlib only | — |
| **Mem0** | `pip install mem0ai` | `MEM0_API_KEY` |
| **Honcho** | `pip install honcho-ai` | `HONCHO_API_KEY`, `HONCHO_APP_ID` |

Missing a backend? No problem — it's silently skipped. No crashes, no noise.

## How routing works

Each backend gets a tool-name prefix (`mnemosyne_`, `mem0_`, etc.). When the model calls `mnemosyne_recall`, the plugin routes it to Mnemosyne. When it calls `holographic_probe`, it goes to Holographic.

All lifecycle hooks (`initialize`, `shutdown`, `prefetch`, `sync_turn`, etc.) fan out to every active sub-provider. Each call is isolated — if one backend throws, the others keep running.

## Config formats

Both of these are equivalent:

```yaml
# Format 1: per-backend options
memory:
  provider: multi
  multi:
    backends:
      mnemosyne: {}
      holographic: {}

# Format 2: concise list
memory:
  provider: multi
  providers:
    - mnemosyne
    - holographic
```

Disable a backend by setting it to `false`:

```yaml
memory:
  multi:
    backends:
      mnemosyne: {}
      mem0: false      # disabled
```

See [CONFIG.md](CONFIG.md) for the full reference.

## Validation

```bash
# Check which backends are detected
python scripts/health_check.py --verbose

# Run with JSON output
python scripts/health_check.py --json
```

## Testing

```bash
# Install test deps
pip install -e ".[all,test]"

# Run the suite
python -m pytest tests/ -v

# With coverage
python -m pytest tests/ --cov=src/multi_memory --cov-report=term-missing
```

## Development

```bash
# Lint
ruff check src/ tests/

# Auto-fix
ruff check src/ tests/ --fix

# Full check (lint + tests + coverage)
make test && ruff check src/ tests/
```

## Project structure

```
src/multi_memory/
├── __init__.py      # register() + MultiMemoryProvider
├── adapters.py      # 4 sub-provider adapters with prefix routing
├── budget.py        # ToolBudgetWarning — schema count monitor
├── config.py        # Config loader helpers
├── discovery.py     # Backend discovery + install detection
├── health.py        # HealthTracker + circuit breaker
└── validate.py      # NamespaceValidator — prefix collision checks
```

## Contributing

1. Fork the repo
2. Create a feature branch
3. Make your changes (tests required)
4. Run `ruff check src/ tests/ && python -m pytest tests/ -q`
5. Open a PR

## License

[AGPL-3.0-or-later](LICENSE)
