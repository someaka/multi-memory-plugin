# Multi-Memory Plugin — Configuration Reference

## Install

```bash
hermes plugins install someaka/multi-memory-plugin
hermes config set memory.provider multi
```

Add backends:

```bash
hermes config set memory.multi.backends.holographic true
hermes config set memory.multi.backends.mnemosyne true
```

After restart, use `hermes multi add <name>` for a cleaner workflow.

Restart Hermes for the new provider to take effect.

---

## Configuration Formats

Two formats are supported. Both are equivalent — choose the one you prefer.

### Format 1: `multi.backends` (per-backend options)

```yaml
memory:
  provider: multi
  multi:
    backends:
      mnemosyne: true            # stdlib-only; no pip install needed
      mem0: true                 # requires MEM0_API_KEY in env
      holographic: true          # stdlib-only
      honcho: true               # requires honcho-ai package
      openviking: true           # requires openviking + running server
      hindsight: true            # requires hindsight-client
      retaindb: true             # requires RETAINDB_API_KEY
      byterover: true            # requires brv CLI (npm)
      supermemory: true          # requires SUPERMEMORY_API_KEY
```

### Format 2: `providers` list (concise)

```yaml
memory:
  provider: multi
  providers:
    - "mnemosyne"
    - "mem0"
    - "holographic"
    - "honcho"
    - "openviking"
    - "hindsight"
    - "retaindb"
    - "byterover"
    - "supermemory"
```

---

## Per-Backend Reference

### Mnemosyne (`mnemosyne`)

| Property | Value |
|----------|-------|
| Python dep | stdlib-only |
| Env vars | None |
| Module | Plugin loader (`~/.hermes/plugins/mnemosyne/`) |
| Tool prefix | `mnemosyne_` |
| Config key | `mnemosyne` |

User-installed plugin. Tools are self-prefixed (`mnemosyne_recall`, `mnemosyne_remember`, etc.).

---

### Mem0 (`mem0`)

| Property | Value |
|----------|-------|
| Python dep | `mem0ai>=0.1` |
| Env vars | `MEM0_API_KEY` |
| Module | `plugins.memory.mem0` |
| Tool prefix | `mem0_` |
| Config key | `mem0` |

Cloud-hosted memory with semantic search. Requires `MEM0_API_KEY`.

---

### Holographic (`holographic`)

| Property | Value |
|----------|-------|
| Python dep | stdlib-only |
| Env vars | None |
| Module | `plugins.memory.holographic` |
| Tool prefix | `holographic_` |
| Config key | `holographic` |

Local SQLite fact store with FTS5 search and HRR compositional queries.

---

### Honcho (`honcho`)

| Property | Value |
|----------|-------|
| Python dep | `honcho-ai` |
| Env vars | `HONCHO_API_KEY`, `HONCHO_APP_ID` |
| Module | `plugins.memory.honcho` |
| Tool prefix | `honcho_` |
| Config key | `honcho` |

AI-native cross-session user modeling with dialectic reasoning.

---

### OpenViking (`openviking`)

| Property | Value |
|----------|-------|
| Python dep | `openviking` |
| Env vars | `OPENVIKING_ENDPOINT` (default: `http://127.0.0.1:1933`) |
| Module | `plugins.memory.openviking` |
| Tool prefix | `viking_` (note: differs from config key) |
| Config key | `openviking` |

Context database with filesystem-style knowledge hierarchy and tiered retrieval.
Tools: `viking_search`, `viking_read`, `viking_browse`, `viking_remember`, `viking_add_resource`.

---

### Hindsight (`hindsight`)

| Property | Value |
|----------|-------|
| Python dep | `hindsight-client` |
| Env vars | `HINDSIGHT_API_KEY` |
| Module | `plugins.memory.hindsight` |
| Tool prefix | `hindsight_` |
| Config key | `hindsight` |

Long-term memory with knowledge graph and entity resolution.
Tools: `hindsight_retain`, `hindsight_recall`, `hindsight_reflect`.

---

### RetainDB (`retaindb`)

| Property | Value |
|----------|-------|
| Python dep | none (uses urllib) |
| Env vars | `RETAINDB_API_KEY` |
| Module | `plugins.memory.retaindb` |
| Tool prefix | `retaindb_` |
| Config key | `retaindb` |

Cloud memory API with hybrid search and delta compression.
Tools: `retaindb_profile`, `retaindb_search`, `retaindb_context`, `retaindb_remember`, `retaindb_forget`.

---

### ByteRover (`byterover`)

| Property | Value |
|----------|-------|
| Python dep | CLI tool (`npm install -g byterover-cli`) |
| Env vars | None (optional `BRV_API_KEY` for cloud sync) |
| Module | `plugins.memory.byterover` |
| Tool prefix | `brv_` (note: differs from config key) |
| Config key | `byterover` |

Persistent memory via the `brv` CLI. Local-first with optional cloud sync.
Tools: `brv_query`, `brv_curate`, `brv_status`.

---

### Supermemory (`supermemory`)

| Property | Value |
|----------|-------|
| Python dep | `supermemory` |
| Env vars | `SUPERMEMORY_API_KEY` |
| Module | `plugins.memory.supermemory` |
| Tool prefix | `supermemory_` |
| Config key | `supermemory` |

Semantic long-term memory with profile recall and session-end graph building.
Tools: `supermemory_store`, `supermemory_search`, `supermemory_forget`, `supermemory_profile`.

---

## Enabling / Disabling Backends

Backends can be enabled or disabled per config by toggling their value:

```yaml
memory:
  multi:
    backends:
      mnemosyne: true         # enabled
      mem0: false             # disabled (explicit false)
      holographic: true       # enabled
      honcho: "false"         # disabled (string form also accepted)
```

A backend is treated as disabled if its value is one of:
- `false` (YAML boolean)
- `"false"` / `"False"` (string)
- `"0"` (string)
- `"no"` (string)
- `0` (integer)
- `null` / `~` (YAML null)
- `""` (empty string)

---

## Development

```bash
# Standard install for local development
hermes plugins install --force someaka/multi-memory-plugin
hermes config set memory.provider multi

# Or for live editing: clone and symlink
git clone https://github.com/someaka/multi-memory-plugin
cd multi-memory-plugin
ln -sf "$(pwd)" ~/.hermes/plugins/multi
hermes config set memory.provider multi

# Test
uv sync --extra test
uv run pytest tests/

# Lint
ruff check src/ tests/
```

---

## Troubleshooting

**Backend not loading?** Check the Hermes logs:
```bash
tail -f ~/.hermes/logs/hermes.log | grep "multi-memory"
```

**ImportError for a backend?** Install the missing package:
```bash
pip install mem0ai            # for Mem0
pip install honcho-ai         # for Honcho
pip install openviking        # for OpenViking
pip install hindsight-client  # for Hindsight
pip install supermemory       # for Supermemory
npm install -g byterover-cli  # for ByteRover
```

Mnemosyne and Holographic are stdlib-only — no install needed.
