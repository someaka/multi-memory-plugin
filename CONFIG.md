# Multi-Memory Plugin — Configuration Reference

## Overview

The multi-memory plugin lets you run multiple memory backends simultaneously via a single
`MemoryProvider` instance. All lifecycle calls (`initialize`, `shutdown`, `prefetch`,
`sync_turn`, etc.) fan out to every active sub-provider with per-provider error isolation.

Configuration is read from `~/.hermes/config.yaml` (or `$HERMES_HOME/config.yaml`).

---

## Configuration Formats

Two formats are supported. Both are equivalent — choose the one you prefer.

### Format 1: `multi.backends` (verbose — per-backend options)

```yaml
memory:
  provider: multi
  multi:
    backends:
      mnemosyne: {}              # stdlib-only; no pip install needed
      mem0: {}                   # requires MEM0_API_KEY in env
      holographic: {}            # stdlib-only
      honcho: {}                 # requires honcho-ai package
```

Each backend value is a dict of per-backend options (currently none are defined, all backends
use `{}`, but the format is future-proof for per-backend tuning).

### Format 2: `providers` list (concise)

```yaml
memory:
  provider: multi
  providers:
    - "mnemosyne"
    - "mem0"
    - "holographic"
    - "honcho"
```

Both formats are accepted by `_normalise_multi_config()`. The `providers` list wins when
both are present.

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

The Mnemosyne backend is a user-installed plugin deployed to
`~/.hermes/plugins/mnemosyne/` (see [AxDSan/mnemosyne](https://github.com/AxDSan/mnemosyne)).
Uses the Hermes plugin loader — no pip install needed. Tools are self-prefixed
(`mnemosyne_recall`, `mnemosyne_remember`, etc.) so the adapter passes them through
without stripping.

**Config example:**
```yaml
memory:
  provider: multi
  multi:
    backends:
      mnemosyne: {}
```

---

### Mem0 (`mem0`)

| Property | Value |
|----------|-------|
| Python dep | `mem0ai>=0.1` |
| Env vars | `MEM0_API_KEY` |
| Module | `plugins.memory.mem0` (bundled) |
| Tool prefix | `mem0_` |
| Config key | `mem0` |

Mem0 provides cloud-hosted memory with semantic search. Requires a Mem0 API key.
Tools are self-prefixed by the provider (`mem0_search`) — the adapter strips
and re-adds the prefix to avoid double-prefixing.

**Config example:**
```yaml
memory:
  provider: multi
  multi:
    backends:
      mem0: {}
```

Requires `MEM0_API_KEY` in the environment, `~/.hermes/.env`, or `~/.hermes/mem0.json`:
```json
{"api_key": "your-mem0-api-key"}
```

---

### Holographic (`holographic`)

| Property | Value |
|----------|-------|
| Python dep | stdlib-only |
| Env vars | None |
| Module | `plugins.memory.holographic.HolographicMemoryProvider` |
| Tool prefix | `holographic_` |
| Config key | `holographic` |

Holographic memory uses local embedding + SQLite-based vector storage (stdlib only).
No external dependencies.

**Config example:**
```yaml
memory:
  provider: multi
  multi:
    backends:
      holographic: {}
```

---

### Honcho (`honcho`)

| Property | Value |
|----------|-------|
| Python dep | `honcho-ai` |
| Env vars | `HONCHO_API_KEY`, `HONCHO_APP_ID` |
| Module | `plugins.memory.honcho.HonchoMemoryProvider` |
| Tool prefix | `honcho_` |
| Config key | `honcho` |

Honcho provides a hosted memory platform. Requires both `HONCHO_API_KEY` and `HONCHO_APP_ID`.

**Config example:**
```yaml
memory:
  provider: multi
  multi:
    backends:
      honcho: {}
```

---

## Enabling / Disabling Backends

Backends can be enabled or disabled per config by toggling their value:

```yaml
memory:
  multi:
    backends:
      mnemosyne: {}        # enabled (empty dict = enabled)
      mem0: false          # disabled (explicit false)
      holographic: {}      # enabled
      honcho: "false"      # disabled (string form also accepted)
```

A backend is treated as disabled if its value is one of:
- `false` (YAML boolean)
- `"false"` / `"False"` (string)
- `"0"` (string)
- `0` (integer)
- `null` / `~` (YAML null)

Any other value (including `{}`, `true`, or a dict with options) = enabled.

---

## Advanced: Custom Hermes Home

Set `HERMES_HOME` in the environment to use a non-default config path:

```bash
export HERMES_HOME=/path/to/custom/hermes
```

The plugin reads `$HERMES_HOME/config.yaml` at initialization time.

---

## Validation

After configuration, validate everything works:

```bash
# Quick health check
python scripts/health_check.py --verbose

# Run test suite
python -m pytest tests/ -v

# Run all health checks as JSON
python scripts/health_check.py --json
```

---

## Troubleshooting

**Backend not loading?** Check the Hermes logs:
```bash
tail -f ~/.hermes/logs/hermes.log | grep "multi-memory"
```

**Unknown backend warning?** Check the config key spelling. Valid keys: `mnemosyne`,
`mem0`, `holographic`, `honcho`.

**ImportError for a backend?** Install the missing package:
```bash
pip install mem0ai     # for Mem0
pip install honcho-ai  # for Honcho
```

Both Mnemosyne and Holographic are stdlib-only — no install needed.
