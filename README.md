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

Hermes normally only lets you use one memory system at a time. This plugin
lets you use several at once.

You tell it which ones you want. It talks to all of them whenever Hermes
needs to remember something or look something up. The answers come back
combined — as if they all came from one place.

If one of them stops working, the plugin notices and skips it. It tries
again after a little while. If it's still broken, it waits longer next
time. The others keep working fine in the meantime.

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
