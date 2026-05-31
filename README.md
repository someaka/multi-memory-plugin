# multi-memory

Run multiple [Hermes](https://github.com/NousResearch/hermes-agent) memory backends at the same time, through a single provider.

[![CI](https://github.com/someaka/multi-memory-plugin/actions/workflows/ci.yml/badge.svg)](https://github.com/someaka/multi-memory-plugin/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: AGPL v3](https://img.shields.io/badge/license-AGPL%20v3-blue.svg)](LICENSE)

---

## Install

```bash
# Symlink into Hermes plugin directory
ln -sf "$(pwd)/src/multi_memory" ~/.hermes/hermes-agent/plugins/memory/multi/

# Add to ~/.hermes/config.yaml
cat >> ~/.hermes/config.yaml << 'EOF'
memory:
  provider: multi
  multi:
    backends:
      mnemosyne: {}
      holographic: {}
EOF

# Restart Hermes
```

Each backend needs its own setup (API keys, packages, etc). See the
[backend table](#backends) below or **[CONFIG.md](CONFIG.md)** for
per-backend details.

---

## How it works

Hermes allows one memory provider at a time. This plugin *is* that one
provider — and it fans out to as many backends as you configure.

```
Model calls: mnemosyne_recall(...)   ──┐
Model calls: viking_search(...)      ──┤
Model calls: brv_query(...)          ──┼──▶  MultiMemoryProvider
Model calls: holographic_store(...)  ──┤         │
Model calls: supermemory_store(...)  ──┘    ┌────┴────┐
                                            ▼         ▼
                                       Mnemosyne  OpenViking  ...
                                            │         │
                                            ▼         ▼
                                          SQLite    Viking DB
```

**Tool routing** — each backend owns a prefix (`mnemosyne_`, `holographic_`,
`mem0_`, `viking_`, `brv_`, …). Tool calls route to the matching backend
automatically.

**Lifecycle fanout** — `initialize`, `shutdown`, `sync_turn`,
`on_session_end`, `on_memory_write`, and every other hook fires on all
active backends. One backend failing doesn't block the rest.

**Circuit breaker** — after 3 consecutive failures a backend is skipped.
After a 30-second cooldown it gets one probe call. If that succeeds, the
circuit closes. If it fails, the cooldown doubles (up to 5 minutes).

**Custom backends** — any `MemoryProvider` implementation dropped into
`plugins/memory/<name>/` is automatically discovered. No code changes
needed, just add its name to config.

**CLI** — `hermes multi status`, `hermes multi list`, `hermes multi add`,
`hermes multi remove`.

---

## Backends

| Backend | What | Install | Env vars |
|:--------|:-----|:--------|:---------|
| **[Mnemosyne](https://github.com/AxDSan/mnemosyne)** | Local SQLite + vector recall | Plugin at `~/.hermes/plugins/mnemosyne/` | — |
| **[Holographic](https://github.com/NousResearch/hermes-agent/tree/main/plugins/memory/holographic)** | SQLite fact store, FTS5, HRR algebra | Built-in (stdlib) | — |
| **[Mem0](https://mem0.ai)** | Cloud semantic search | `pip install mem0ai` | `MEM0_API_KEY` |
| **[Honcho](https://app.honcho.dev)** | Cross-session user modeling | `pip install honcho-ai` | `HONCHO_API_KEY` `HONCHO_APP_ID` |
| **[OpenViking](https://github.com/volcengine/OpenViking)** | Context database, filesystem hierarchy | `pip install openviking` + server | `OPENVIKING_ENDPOINT` |
| **[Hindsight](https://hindsight.vectorize.io)** | Knowledge graph + entity resolution | `pip install hindsight-client` | `HINDSIGHT_API_KEY` |
| **[RetainDB](https://retaindb.com)** | Cloud hybrid search | — (stdlib urllib) | `RETAINDB_API_KEY` |
| **[ByteRover](https://byterover.dev)** | CLI-first local knowledge tree | `npm install -g byterover-cli` | — |
| **[Supermemory](https://supermemory.ai)** | Semantic long-term graph memory | `pip install supermemory` | `SUPERMEMORY_API_KEY` |

Backends you haven't installed are skipped with a warning in the logs.

---

## Configuration

Two equivalent formats:

```yaml
# Dict — per-backend options
memory:
  provider: multi
  multi:
    backends:
      mnemosyne: {}
      mem0: {}
      holographic: false   # disabled without removing

# List — concise
memory:
  provider: multi
  providers:
    - mnemosyne
    - mem0
```

Full reference: **[CONFIG.md](CONFIG.md)**

---

## Development

```bash
pip install -e ".[all,test]"
python -m pytest tests/ -v
ruff check src/ tests/
```

## Docs

- **[CONFIG.md](CONFIG.md)** — per-backend config reference
- **[AGENT.md](AGENT.md)** — instructions for AI coding assistants
- **[CHANGELOG.md](CHANGELOG.md)** — version history
- **[CORE-INTEGRATION-SPEC.md](CORE-INTEGRATION-SPEC.md)** — architecture and upstream design

## License

[AGPL-3.0-or-later](LICENSE)
