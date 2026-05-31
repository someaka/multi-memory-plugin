# Multi-Memory Plugin: Core Integration Spec

## The Design

The upstream MemoryManager has a **one-external-provider limit**. This is deliberate. The multi-memory plugin exists to be that one provider — it manages multiple backends internally so the core doesn't have to.

The plugin works with upstream as-is. No core changes are required.

## What Could Be Proposed Upstream (Optional)

Two improvements that benefit ALL providers, not just the plugin:

### 1. Thread Safety (~15 lines)

The MemoryManager has no lock. In gateway mode, `add_provider()` and lifecycle hooks run concurrently — race condition on `_providers` list and `_tool_to_provider` dict.

```python
import threading

class MemoryManager:
    def __init__(self):
        self._lock = threading.RLock()

    def add_provider(self, provider):
        with self._lock:
            # existing logic
```

**Why upstream benefits:** Any provider (Honcho, Mem0, Mnemosyne) running in gateway mode has the same race. This is a correctness fix, not a feature request.

### 2. `remove_provider()` (~25 lines)

You can `add_provider()` but never remove. Long-running agents (gateway, cron) can't hot-swap.

**Why upstream benefits:** Completes the API. Any long-running agent needs this.

### 3. `logger.debug` → `logger.warning` in lifecycle hooks (~10 lines)

The core's lifecycle hooks swallow exceptions at debug level. If a provider fails, nobody knows.

**Why upstream benefits:** All providers fail silently today.

**Total: ~50 lines, backwards-compatible, no API changes.**

---

## What the Plugin Adds (Not Core's Problem)

| Feature | Why Plugin |
|---|---|
| 9 backend adapters | Core doesn't know about specific backends |
| Circuit breaker / health tracking | Proactive failure detection for multi-backend |
| Tool budget warnings | Multiple backends = more tools |
| Namespace validation | Prefix collision risk |
| Backend discovery + loading | Scan for installed backends |
| Config normalization (3 formats) | Multiple config conventions |
| close() vs shutdown() | Connection pool cleanup |
| Holographic double-prefix fix | Adapter logic |
| Runtime add/remove sub-providers | Plugin manages its own internal list |

---

## Summary

| Category | Count |
|---|---|
| Core changes REQUIRED | **0** |
| Core improvements worth proposing | **3** (~50 lines total) |
| Plugin-only features | **9+** |
