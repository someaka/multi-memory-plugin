# multi-memory

> Run every [Hermes](https://github.com/NousResearch/hermes-agent) memory backend at once — through a single provider.

[![CI](https://github.com/someaka/multi-memory-plugin/actions/workflows/ci.yml/badge.svg)](https://github.com/someaka/multi-memory-plugin/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: AGPL v3](https://img.shields.io/badge/license-AGPL%20v3-blue.svg)](LICENSE)

Hermes only activates one memory provider at a time. This plugin changes that.
Drop it in, list the backends you want, and they all run together — tool calls
route to the right one automatically, lifecycle hooks fan out to every active
provider, and one backend crashing won't take down the rest.

---

## Supported backends

| Backend | What it is | Install | Env vars |
|:--------|:-----------|:--------|:---------|
| **[Mnemosyne](https://github.com/AxDSan/mnemosyne)** | Local SQLite + vector recall | Plugin at `~/.hermes/plugins/mnemosyne/` | — |
| **Holographic** | SQLite fact store, FTS5, HRR compositional algebra | Built-in (stdlib) | — |
| **[Mem0](https://mem0.ai)** | Cloud semantic search with auto-extraction | `pip install mem0ai` | `MEM0_API_KEY` |
| **[Honcho](https://app.honcho.dev)** | Hosted cross-session user modeling | `pip install honcho-ai` | `HONCHO_API_KEY` `HONCHO_APP_ID` |
| **[OpenViking](https://github.com/volcengine/OpenViking)** | Context database with filesystem-style hierarchy | `pip install openviking` + server | `OPENVIKING_ENDPOINT` |
| **[Hindsight](https://hindsight.vectorize.io)** | Knowledge graph with entity resolution | `pip install hindsight-client` | `HINDSIGHT_API_KEY` |
| **[RetainDB](https://retaindb.com)** | Cloud hybrid search with delta compression | — (stdlib urllib) | `RETAINDB_API_KEY` |
| **[ByteRover](https://byterover.dev)** | CLI-first local knowledge tree | `npm install -g byterover-cli` | — |
| **[Supermemory](https://supermemory.ai)** | Semantic long-term graph memory | `pip install supermemory` | `SUPERMEMORY_API_KEY` |

Backends you haven't installed are skipped with a **warning in the logs** —
missing package, missing API key, or failed import. Nothing disappears silently.

---

## Quick start

```bash
# 1. Install — symlink stays in sync with the repo
ln -sf "$(pwd)/src/multi_memory" ~/.hermes/hermes-agent/plugins/memory/multi/

# 2. Configure — add to ~/.hermes/config.yaml
cat >> ~/.hermes/config.yaml << 'EOF'
memory:
  provider: multi
  multi:
    backends:
      mnemosyne: {}
      holographic: {}
EOF

# 3. Restart Hermes. Done.
```

Add more backends by uncommenting or adding their entries. Each one needs its
own setup — see the table above for install commands and env vars.

---

## How it works

```
Model calls: mnemosyne_recall(...)   ──┐
Model calls: viking_search(...)      ──┤
Model calls: brv_query(...)          ──┼──▶  MultiMemoryProvider
Model calls: supermemory_store(...)  ──┤         │
                                       │    ┌────┴────┐
                                       │    ▼         ▼
                                       │ Mnemosyne  OpenViking  ...
                                       │    │         │
                                       │    ▼         ▼
                                       │  SQLite    Viking DB
```

**Prefix routing** — each backend owns a tool-name prefix (`mnemosyne_`,
`mem0_`, `viking_`, `brv_`, `hindsight_`, …). The model's tool call is
routed to the matching backend by prefix. First match wins.

> **Note:** config key and tool prefix can differ. ByteRover is `byterover`
> in config but `brv_` on tools. OpenViking is `openviking` in config but
> `viking_` on tools.

**Lifecycle fanout** — `initialize`, `shutdown`, `prefetch`, `sync_turn`,
`on_session_end`, and every other hook fires on all active backends. One
backend failing doesn't block the others. Every failure is logged at
WARNING level with the backend name and exception.

**Circuit breaker** — after 3 consecutive failures a backend is skipped
until it succeeds again. Prevents a broken backend from slowing down
every turn.

---

## Configuration

Two equivalent formats — use whichever you prefer:

```yaml
# Verbose — per-backend options, future-proof
memory:
  provider: multi
  multi:
    backends:
      mnemosyne: {}
      mem0: {}
      holographic: {}
      honcho: {}

# Concise — list of names
memory:
  provider: multi
  providers:
    - mnemosyne
    - mem0
    - holographic
    - honcho
```

Disable a backend without removing it:

```yaml
memory:
  multi:
    backends:
      mnemosyne: {}
      mem0: false        # disabled
      holographic: {}
```

Values that disable: `false`, `"false"`, `"False"`, `"0"`, `0`, `null`, `~`.
Everything else (including `{}` and `true`) means enabled.

See **[CONFIG.md](CONFIG.md)** for the full per-backend reference.

---

## Health check

```bash
# Which backends are detected on this system?
python scripts/health_check.py --verbose

# Machine-readable JSON output
python scripts/health_check.py --json
```

---

## Development

```bash
# Install with all backends + test deps
pip install -e ".[all,test]"

# Run the test suite
python -m pytest tests/ -v

# Lint
ruff check src/ tests/

# Auto-fix
ruff check src/ tests/ --fix

# Coverage
python -m pytest tests/ --cov=multi_memory --cov-report=term-missing

# Full pipeline
make test && ruff check src/ tests/
```

---

## Project structure

```
src/multi_memory/
├── __init__.py      # register() + MultiMemoryProvider — the orchestrator
├── adapters.py      # 9 adapter classes — one per backend, prefix routing
├── budget.py        # ToolBudgetWarning — warns when schema count gets high
├── config.py        # load_multi_config(), get_enabled_backends()
├── discovery.py     # discover_backends() — probe what's installed
├── health.py        # HealthTracker + circuit breaker + timeout wrapper
├── validate.py      # NamespaceValidator — catches prefix collisions
└── py.typed         # PEP 561 marker
```

---

## Contributing

1. Fork → feature branch
2. `ruff check src/ tests/ && python -m pytest tests/ -q`
3. Open a PR — tests required for new backends

---

## License

[AGPL-3.0-or-later](LICENSE)
