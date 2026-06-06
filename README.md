# multi-memory

A [Hermes](https://github.com/NousResearch/hermes-agent) memory provider that runs multiple memory backends at once.

[![CI](https://github.com/someaka/multi-memory-plugin/actions/workflows/ci.yml/badge.svg)](https://github.com/someaka/multi-memory-plugin/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: AGPL v3](https://img.shields.io/badge/license-AGPL%20v3-blue.svg)](LICENSE)

---

## Install

```bash
hermes plugins install someaka/multi-memory-plugin
hermes config set memory.provider multi
```

Then pick your backends with the interactive setup wizard:

```bash
hermes multi setup
```

Or add backends directly:

```bash
hermes multi add holographic
hermes multi add mnemosyne
```

Restart Hermes. The provider auto-discovers installed backends.

---

## How it works

Hermes only lets one memory provider be active. This plugin is that one
provider — it delegates to as many backends as you list.

Every Hermes memory backend works: Holographic, Mnemosyne, Mem0, Honcho,
OpenViking, Hindsight, RetainDB, ByteRover, Supermemory, and any
third-party backend dropped into `plugins/memory/<name>/`. The plugin
auto-discovers them — no code changes needed, just add the name.

When the model calls a memory tool (like `mnemosyne_recall` or
`holographic_store`), the plugin routes it to the right backend by matching
the tool name prefix. Lifecycle hooks (`initialize`, `shutdown`,
`sync_turn`, `on_session_end`, etc.) fire on every active backend. If one
backend fails, the others keep working.

A circuit breaker protects against broken backends: 3 consecutive failures
opens the circuit, the backend is skipped for 30 seconds, then gets one
probe call. If the probe succeeds, the circuit closes. If it fails, the
cooldown doubles (up to 5 minutes).

---

## CLI

Available after restarting Hermes:

```bash
hermes multi setup            # interactive curses-based setup wizard
hermes multi setup <name>     # configure a specific backend interactively
hermes multi status           # active backends + health + plugin status
hermes multi list             # all backends, active markers
hermes multi add <name>       # add a backend to config
hermes multi remove <name>    # remove a backend from config
```

The setup wizard walks through per-backend configuration (API keys, model
choices, endpoint URLs) and auto-installs Python dependencies from each
backend's `plugin.yaml`.

---

## Docs

- **[CONFIG.md](CONFIG.md)** — config formats, per-backend reference, troubleshooting
- **[CONTRIBUTING.md](CONTRIBUTING.md)** — setup, tests, adding backends, architecture
- **[AGENT.md](AGENT.md)** — instructions for AI coding assistants
- **[CHANGELOG.md](CHANGELOG.md)** — version history

## License

[AGPL-3.0-or-later](LICENSE)
