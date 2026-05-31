# Multi-Memory Plugin: What Actually Needs to Change

## TL;DR

**Zero core changes required.** The upstream MemoryManager already handles everything the plugin needs. The plugin implements `MemoryProvider`, registers once, and the core calls all lifecycle hooks, tools, and context fencing automatically.

---

## What the Upstream Core Already Has

The `agent/memory_manager.py` MemoryManager (640 lines) already provides:

| Feature | Core Implementation | Plugin Impact |
|---|---|---|
| Context fencing | `build_memory_context_block()` wraps in `<memory-context>` | Plugin's `prefetch()` output gets wrapped automatically |
| Streaming scrubber | `StreamingContextScrubber` class | Core strips memory-context from streaming output |
| Stale block stripping | `sanitize_context()` | Core strips old blocks before injecting new ones |
| Metadata write introspection | `_provider_memory_write_metadata_mode()` | Core detects keyword/positional/legacy automatically |
| Sync messages introspection | `_provider_sync_accepts_messages()` | Core passes `messages` kwarg when provider supports it |
| `hermes_home` injection | Passed via `initialize(**kwargs)` | Plugin gets it automatically |
| `on_session_switch` empty guard | `if not new_session_id: return` | Core guards before calling providers |
| Tool routing | `has_tool()` + `handle_tool_call()` | Core routes tool calls to plugin |
| Tool schema collection | `get_all_tool_schemas()` with dedup | Core collects plugin schemas |
| Lifecycle hooks | All 8 hooks called on all providers | Plugin receives all hooks |
| Prefetch / sync | `prefetch_all()`, `sync_all()` | Core orchestrates across providers |
| System prompt | `build_system_prompt()` | Core collects plugin's prompt block |
| `add_provider()` | With tool name indexing | Plugin registers once |
| `get_provider()` / `providers` | Name lookup + list | Core manages provider registry |
| Toolset bypass | Memory tools use agent-level handler | Memory tools always visible |

**The core is feature-complete for the plugin's needs.**

---

## What the Core is MISSING (Not Needed by Plugin, But Worth Fixing)

### 1. No `remove_provider()` on MemoryManager

The core can add providers but can't remove them at runtime. The plugin doesn't need this because it manages its own sub-providers internally — the core only sees one provider ("multi").

**Impact:** None for the plugin. Would be useful if someone wanted to hot-swap the entire memory provider at runtime.

### 2. Silent failures in core lifecycle hooks

The core's MemoryManager uses `logger.debug` for lifecycle hook exceptions — the same pattern we fixed in the plugin. If a provider fails in `on_turn_start()`, `sync_turn()`, `on_session_end()`, etc., the failure is invisible unless debug logging is enabled.

**Impact:** Providers can fail silently. Users won't know their memory backend is broken.

**Fix:** `logger.debug` → `logger.warning` in MemoryManager lifecycle hooks. ~10 lines.

---

## The Plugin's Actual Value Proposition

The plugin isn't needed because the core lacks features. It's needed because the core's MemoryManager has a **one-external-provider limit**:

```python
# agent/memory_manager.py:267
if not is_builtin:
    if self._has_external:
        logger.warning(
            "Rejected memory provider '%s' — external provider '%s' is "
            "already registered. Only one external memory provider is "
            "allowed at a time.",
            provider.name, existing,
        )
        return
```

The plugin solves this by being **one provider that fans out to many backends**. The core sees one provider; the plugin manages the multi-backend complexity internally.

### What the plugin adds on top of the core:

| Plugin Feature | Why Core Doesn't Need It |
|---|---|
| 9 backend adapters (Mem0, Honcho, Mnemosyne, etc.) | Core doesn't know about specific backends |
| Circuit breaker / health tracking | Core has basic try/except; plugin adds proactive failure detection |
| Tool budget warnings | Plugin-specific concern (multiple backends = more tools) |
| Namespace validation | Plugin-specific (multiple backends = prefix collision risk) |
| Backend discovery + loading | Plugin-specific (scan for installed backends) |
| Runtime add/remove sub-providers | Plugin manages its own `_subs` list |
| Config normalization (3 formats) | Plugin-specific (multiple config conventions) |
| close() vs shutdown() preference | Plugin-specific (connection pool cleanup) |
| Holographic double-prefix fix | Plugin-specific adapter logic |
| No silent failures (all WARNING) | Plugin improvement over core's debug-level logging |

---

## What to Tell the Lead Dev

1. **No core changes needed.** The plugin works with the existing MemoryManager as-is.

2. **The only improvement worth proposing upstream:** promote `logger.debug` → `logger.warning` in MemoryManager lifecycle hooks. This benefits ALL providers, not just the plugin. ~10 lines, no API change.

3. **Optional nice-to-have:** `remove_provider()` on MemoryManager. Not needed by the plugin, but completes the API symmetry. ~15 lines.

4. **The plugin handles the "interference between backends" problem** that the lead dev doesn't want to deal with: circuit breaker, health tracking, namespace validation, prefix management, tool budget warnings. The core's MemoryManager is a dumb pipe; the plugin is the smart manager.

---

## Summary

| Category | Count | Details |
|---|---|---|
| Core changes REQUIRED | **0** | Plugin works as-is |
| Core improvements WORTH PROPOSING | **1** | `logger.debug` → `logger.warning` (~10 lines) |
| Core nice-to-have | **1** | `remove_provider()` (~15 lines) |
| Plugin-only features | **10+** | All multi-backend complexity |
