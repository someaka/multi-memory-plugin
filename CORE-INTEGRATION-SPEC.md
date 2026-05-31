# Multi-Memory Plugin: Core Integration Spec

## The Real Picture

The upstream MemoryManager (NousResearch, 640 lines) has all the *features* — context fencing, streaming scrubber, metadata introspection, lifecycle hooks, tool routing. The plugin works with upstream as-is because the plugin is ONE external provider that fans out internally.

But the fork (someaka) added three things the upstream lacks:

| Fork Addition | Upstream Status | Impact |
|---|---|---|
| `threading.RLock` | No lock — not thread-safe | Gateway mode (concurrent requests) can corrupt `_providers` list |
| `remove_provider()` | Can add but not remove | No runtime hot-unplug of providers |
| Multi-external-provider support | Hard limit: one external provider | Plugin works around this, but direct multi-provider config doesn't |

## What to Propose Upstream

These three changes are **not plugin-specific** — they improve the MemoryManager for ALL providers. Each is small, backwards-compatible, and addresses a real gap.

### 1. Thread Safety (~15 lines)

**Problem:** The MemoryManager's `_providers` list and `_tool_to_provider` dict are mutated by `add_provider()` and read by every lifecycle hook. In gateway mode, multiple requests run concurrently. No lock protects these structures.

**Fix:** Add `threading.RLock`, snapshot under lock before iterating (same pattern the plugin uses).

```python
import threading

class MemoryManager:
    def __init__(self):
        self._lock = threading.RLock()
        # ...

    def add_provider(self, provider):
        with self._lock:
            # existing logic
            self._providers.append(provider)

    def prefetch_all(self, query, **kwargs):
        with self._lock:
            providers = list(self._providers)
        for provider in providers:  # iterate outside lock
            # ...
```

**Why it matters for upstream:** Any memory provider (Honcho, Mem0, Mnemosyne) running in gateway mode has the same race condition. This isn't a plugin problem — it's a core correctness problem.

### 2. `remove_provider()` (~25 lines)

**Problem:** You can `add_provider()` but never remove one. If a provider fails or the user wants to swap, the only option is restarting the agent.

**Fix:**

```python
def remove_provider(self, name: str) -> bool:
    """Deregister a memory provider by name. Returns True if removed."""
    if name == "builtin":
        logger.warning("Cannot remove builtin memory provider")
        return False
    with self._lock:
        target = None
        remaining = []
        for p in self._providers:
            if p.name == name:
                target = p
            else:
                remaining.append(p)
        if target is None:
            return False
        self._providers = remaining
        # Clean up tool mappings
        tools_to_remove = [t for t, prov in self._tool_to_provider.items() if prov is target]
        for t in tools_to_remove:
            del self._tool_to_provider[t]
    # Shutdown outside lock
    try:
        target.shutdown()
    except Exception as e:
        logger.warning("Provider '%s' shutdown failed: %s", name, e)
    return True
```

**Why it matters for upstream:** Completes the API. `add_provider()` without `remove_provider()` is a half-feature. Any long-running agent (gateway, cron) needs the ability to hot-swap providers.

### 3. Multi-External-Provider Support (~5 lines changed)

**Problem:** The upstream MemoryManager rejects a second `add_provider()` call for non-builtin providers. This forces the plugin to be a single meta-provider that internally manages multiple backends — an extra layer of indirection.

**Fix:** Remove the `_has_external` gate. Allow multiple external providers. Keep duplicate-name rejection.

```python
# Before (upstream):
if not is_builtin:
    if self._has_external:
        logger.warning("Rejected '%s' — '%s' already registered. Only one allowed.", ...)
        return
    self._has_external = True

# After:
if any(p.name == provider.name for p in self._providers):
    logger.warning("Duplicate provider name '%s', ignoring.", provider.name)
    return
```

**Why it matters for upstream:** Users who want Mnemosyne + Honcho + Mem0 simultaneously shouldn't need a meta-provider wrapper. The MemoryManager already fans out to all providers — removing the artificial limit is natural.

---

## What the Plugin Adds (Not a Core Concern)

These are plugin-specific and should NOT go into core:

| Plugin Feature | Why It Stays in Plugin |
|---|---|
| 9 backend adapters | Core doesn't know about specific backends |
| Circuit breaker / health tracking | Plugin's proactive failure detection for multi-backend |
| Tool budget warnings | Plugin-specific (multiple backends = more tools) |
| Namespace validation | Plugin-specific (prefix collision risk) |
| Backend discovery + loading | Plugin-specific (scan for installed backends) |
| Config normalization (3 formats) | Plugin-specific (multiple config conventions) |
| close() vs shutdown() preference | Plugin-specific (connection pool cleanup) |
| Holographic double-prefix fix | Plugin adapter logic |
| Runtime add/remove sub-providers | Plugin manages its own internal list |

---

## What the Lead Dev Gets

1. **Thread-safe MemoryManager** — fixes a real bug in gateway mode, not a plugin nicety
2. **Complete API** — `add_provider()` + `remove_provider()` symmetry
3. **No artificial limits** — multiple external providers work without a meta-provider wrapper
4. **No plugin-specific code in core** — all three changes benefit any provider, not just the multi-memory plugin
5. **Backwards compatible** — existing single-provider configs work unchanged

**Total core changes: ~45 lines across one file (`agent/memory_manager.py`).**
