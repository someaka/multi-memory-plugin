# Multi-Memory Plugin: Core Integration Spec

**Purpose:** What the multi-memory plugin needs from hermes core, verified against actual codebase.

**Principle:** Core provides the plumbing, plugin provides the policy. Core knows nothing about memory backend conflicts, circuit breakers, or multi-provider fan-out.

---

## 1. What Core Already Handles (No Changes Needed)

| Capability | Evidence |
|---|---|
| CLI command registration | `plugins/memory/__init__.py:331` — `discover_plugin_cli_commands()` scans for `cli.py` with `register_cli()`. Plugin ships its own `cli.py`. |
| `toolsets_enabled` filter | `agent_init.py:1183` — checks `agent.enabled_toolsets` before injecting memory schemas. `memory_manager.py:518` — `get_all_tool_schemas()` returns `[]` when `'memory' not in toolsets_enabled`. |
| `hermes_home` injection | `memory_manager.py:743-745` — `initialize_all()` auto-injects `hermes_home` into kwargs. ABC documents it as guaranteed. |
| Context fencing | `memory_manager.py:232-246` — `build_memory_context_block()` wraps prefetch in `<memory-context>` blocks. `sanitize_context()` strips stale fences. |
| Streaming scrubber | `memory_manager.py:67-229` — `StreamingContextScrubber` state machine in `run_agent.py:3729` pipeline. Runs automatically. |

---

## 2. What the Plugin Already Handles

| Capability | Plugin Location |
|---|---|
| Multi-provider fan-out | `__init__.py` — iterates `_subs` |
| Thread safety (RLock + snapshot) | `__init__.py` — `_lock` |
| Circuit breaker | `health.py` — `HealthTracker` |
| Tool budget warning | `budget.py` — `ToolBudgetWarning` |
| Namespace validation | `validate.py` — `NamespaceValidator` |
| Backend discovery | `discovery.py` — `discover_backends()` |
| 9 adapter classes | `adapters.py` |
| Metadata write mode introspection | `adapters.py` — `_metadata_write_mode()` |
| Sync messages introspection | `adapters.py` — `_sync_accepts_messages()` |
| Runtime add/remove providers | `__init__.py` — `add_provider()` / `remove_provider()` |
| All 8 lifecycle hooks | `__init__.py` |
| Config normalization (3 formats) | `config.py` |
| close() preference | `adapters.py` + `__init__.py` |

---

## 3. The One Genuine Gap: Schema Refresh After Runtime Changes

### Problem

When the plugin calls `remove_provider("holographic")` or `add_provider(new_adapter)` at runtime, the tool schema list changes. But `agent.tools` was built once at `agent_init.py:1191` and never refreshed. The removed provider's tools remain in the LLM's tool list (stale), and new providers' tools are missing.

### Why This Is the Only Real Gap

- `memory_manager.get_all_tool_schemas()` is NOT cached internally — it iterates providers fresh each call
- BUT the caller (`agent_init.py:1191`) only calls it once and stores the result in `agent.tools`
- `agent.tools` is used directly by `chat_completion_helpers.py:529` for every API call
- The plugin has no reference to `agent.tools` and can't modify it

### Workaround (No Core Changes)

The plugin's circuit breaker already handles the failure case gracefully:
- Removed provider's tools stay in `agent.tools` but calls to them fail
- The plugin catches the failure, records it in health tracking, and returns an error message
- After `failure_limit` consecutive failures, the circuit opens and the tool is silently skipped
- This is functional but not ideal — the LLM sees tools it can't use

### If Core Wants to Fix This

**Option A (minimal):** One-line change in `agent_init.py` or `conversation_loop.py`:
```python
# Before building the API tools list, refresh memory schemas
if agent.memory_manager:
    memory_schemas = agent.memory_manager.get_all_tool_schemas(
        toolsets_enabled=agent.enabled_toolsets
    )
    # Replace stale memory tools in agent.tools
    agent.tools = [t for t in agent.tools if not t.get("function", {}).get("name", "").startswith(MEMORY_PREFIXES)]
    agent.tools.extend(memory_schemas)
```

**Option B (cleaner):** Add a `refresh_memory_tools()` method on the agent that rebuilds just the memory portion of `agent.tools`. Call it from `on_session_switch()` or whenever the plugin signals a change.

**Option C (laziest):** Don't cache `agent.tools` at all — rebuild the full tools list from all providers on every API call. This has a small perf cost but eliminates the caching problem entirely.

---

## 4. Summary

**Core already does 5 of the 7 things the old spec claimed it didn't.** The remaining items (context fencing, streaming scrubber, toolsets, hermes_home, CLI) are all implemented and working.

**The plugin handles everything at the multi-provider level** — fan-out, circuit breaker, health tracking, runtime management, introspection, config normalization.

**The only gap** is that `agent.tools` is built once at init and not refreshed when the plugin adds/removes sub-providers at runtime. The circuit breaker workaround is functional. A proper fix is a one-line change in core to refresh memory schemas on session switch.

**Total core changes needed: 0-1 lines** (optional schema refresh). Everything else is already done.
