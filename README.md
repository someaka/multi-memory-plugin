# multi-memory

A [Hermes](https://github.com/NousResearch/hermes-agent) memory provider that runs multiple memory backends at once.

[![CI](https://github.com/someaka/multi-memory-plugin/actions/workflows/ci.yml/badge.svg)](https://github.com/someaka/multi-memory-plugin/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: AGPL v3](https://img.shields.io/badge/license-AGPL%20v3-blue.svg)](LICENSE)

---

## Install

```bash
hermes plugins install someaka/multi-memory-plugin
```

Then configure which backends to activate:

```bash
hermes memory setup
```

Or edit `~/.hermes/config.yaml` directly:

```yaml
memory:
  provider: multi
  multi:
    backends:
      holographic: {}
      mnemosyne: {}
      mem0: {}
```

Restart Hermes. Each backend needs its own setup — API keys, packages, etc.
See **[CONFIG.md](CONFIG.md)** for per-backend details.

---

## How it works

Hermes only lets one memory provider be active. This plugin is that one
provider — it delegates to as many backends as you list in config.

When the model calls a memory tool (like `mnemosyne_recall` or
`holographic_store`), the plugin routes it to the right backend by matching
the tool name prefix. Lifecycle hooks (`initialize`, `shutdown`,
`sync_turn`, `on_session_end`, etc.) fire on every active backend. If one
backend fails, the others keep working.

A circuit breaker protects against broken backends: 3 consecutive failures
opens the circuit, the backend is skipped for 30 seconds, then gets one
probe call. If the probe succeeds, the circuit closes. If it fails, the
cooldown doubles (up to 5 minutes).

Any `MemoryProvider` dropped into `plugins/memory/<name>/` is
auto-discovered — no code changes needed. Just add the name to config.

---

## Backends

| Backend | What | Install | Env vars |
|:--------|:-----|:--------|:---------|
| **[Holographic](https://github.com/NousResearch/hermes-agent/tree/main/plugins/memory/holographic)** | SQLite fact store, FTS5, HRR algebra | Built-in | — |
| **[Mnemosyne](https://github.com/AxDSan/mnemosyne)** | Local SQLite + vector recall | Plugin | — |
| **[Mem0](https://mem0.ai)** | Cloud semantic search | `pip install mem0ai` | `MEM0_API_KEY` |
| **[Honcho](https://app.honcho.dev)** | Cross-session user modeling | `pip install honcho-ai` | `HONCHO_API_KEY` `HONCHO_APP_ID` |
| **[OpenViking](https://github.com/volcengine/OpenViking)** | Context database | `pip install openviking` + server | `OPENVIKING_ENDPOINT` |
| **[Hindsight](https://hindsight.vectorize.io)** | Knowledge graph | `pip install hindsight-client` | `HINDSIGHT_API_KEY` |
| **[RetainDB](https://retaindb.com)** | Cloud hybrid search | — | `RETAINDB_API_KEY` |
| **[ByteRover](https://byterover.dev)** | CLI knowledge tree | `npm install -g byterover-cli` | — |
| **[Supermemory](https://supermemory.ai)** | Semantic graph memory | `pip install supermemory` | `SUPERMEMORY_API_KEY` |

---

## CLI

```bash
hermes multi status          # active backends + config format
hermes multi list            # all 9 backends, active markers
hermes multi add <name>      # add a backend to config
hermes multi remove <name>   # remove a backend from config
```

---

## Configuration

Two equivalent formats:

```yaml
# Dict
memory:
  provider: multi
  multi:
    backends:
      holographic: {}
      mem0: {}
      mem0: false        # disabled

# List
memory:
  provider: multi
  providers:
    - holographic
    - mem0
```

Disable a backend without removing: set it to `false`, `"false"`, `"0"`,
`0`, or `null`.

Full reference: **[CONFIG.md](CONFIG.md)**

---

## Development

```bash
# Symlink for live editing
ln -sf "$(pwd)/src/multi_memory" ~/.hermes/hermes-agent/plugins/memory/multi/

# Test
pip install -e ".[all,test]"
python -m pytest tests/ -v

# Lint
ruff check src/ tests/
```

## Docs

- **[CONFIG.md](CONFIG.md)** — per-backend config reference
- **[AGENT.md](AGENT.md)** — instructions for AI coding assistants
- **[CHANGELOG.md](CHANGELOG.md)** — version history
- **[CORE-INTEGRATION-SPEC.md](CORE-INTEGRATION-SPEC.md)** — architecture and upstream design

## License

[AGPL-3.0-or-later](LICENSE)
