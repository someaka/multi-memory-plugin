# Multi-Memory Plugin: Core Integration Spec

**Purpose:** Define what the multi-memory plugin needs from hermes core. Everything below is the *minimum* core surface the plugin requires to fully replace the fork's MemoryManager functionality.

**Principle:** Core provides the plumbing, plugin provides the policy. Core should know *nothing* about memory backend conflicts, circuit breakers, or multi-provider fan-out. The plugin handles all of that.

---

## 1. What the Plugin Already Handles (No Core Changes Needed)

The plugin implements everything at the provider/multi-provider level:

| Capability | Plugin Location |
|---|---|
| Multi-provider fan-out | `__init__.py` — iterates `_subs` |
| Thread safety (RLock + snapshot) | `__init__.py` — `_lock` |
| Circuit breaker (skip failing backends) | `health.py` — `HealthTracker` |
| Tool budget warning | `budget.py` — `ToolBudgetWarning` |
| Namespace validation | `validate.py` — `NamespaceValidator` |
| Backend discovery | `discovery.py` — `discover_backends()` |
| 9 adapter classes (prefix management) | `adapters.py` |
| Metadata write mode introspection | `adapters.py` — `_metadata_write_mode()` |
| Sync messages introspection | `adapters.py` — `_sync_accepts_messages()` |
| Runtime add/remove providers | `__init__.py` — `add_provider()` / `remove_provider()` |
| Tool introspection | `__init__.py` — `get_all_tool_names()` / `has_tool()` |
| All 8 lifecycle hooks | `__init__.py` |
| Config normalization (3 formats) | `config.py` |
| close() preference over shutdown() | `adapters.py` + `__init__.py` |

---

## 2. What MUST Be in Core (Plugin Cannot Physically Do These)

### 2.1 Tool Schema Re-registration

**Problem:** When the plugin calls `remove_provider("holographic")` at runtime, the tool schemas change. But the MemoryManager has already cached the schemas from `get_tool_schemas()` at session start. The removed provider's tools will still appear in the LLM's tool list, but calls to them will fail.

**What core needs:**
- Either: re-call `get_tool_schemas()` after each `on_session_switch()` / periodically
- Or: expose a `request_schema_refresh()` method on MemoryManager that the plugin can call after `remove_provider()` / `add_provider()`
- Or: make `get_tool_schemas()` lazy — always call it fresh when building the tool list for the LLM

**Recommended approach:** Lazy evaluation. Don't cache schemas. Call `get_tool_schemas()` each time the agent loop needs the tool list. The plugin already deduplicates internally.

### 2.2 `toolsets_enabled` Filtering

**Problem:** The agent loop has a concept of "toolsets" (a set of enabled tool categories like `"memory"`, `"web"`, `"terminal"`). When `"memory"` is not in `toolsets_enabled`, memory tools should be hidden from the LLM. The fork's MemoryManager does this filtering in `get_all_tool_schemas()`. The plugin can't — it doesn't know about toolsets.

**What core needs:**
- The MemoryManager (or wherever schemas are collected) should check `toolsets_enabled` before calling `get_tool_schemas()` on any provider
- If `"memory" not in toolsets_enabled`, skip the memory provider entirely
- This is a one-line check in core: `if "memory" not in toolsets_enabled: continue`

**Recommended approach:** Add the check in `MemoryManager.get_all_tool_schemas()` (or equivalent). No provider API changes needed.

### 2.3 Context Fencing

**Problem:** The fork wraps prefetch results in `<memory-context>` fenced blocks with a system note before injecting into the LLM prompt. It also has `StreamingContextScrubber` to handle split tags across streaming deltas and `sanitize_context()` to strip stale fences. The plugin has no access to the message assembly pipeline.

**What core needs:**
- A hook or wrapper in the message assembly code (where prefetch results get injected into the system prompt or user message) that:
  1. Wraps memory output in a fenced block: `<memory-context>\n{system_note}\n{content}\n</memory-context>`
  2. Strips stale `<memory-context>` blocks before injecting new ones
  3. Handles streaming: `StreamingContextScrubber` or equivalent that tracks partial `</memory-context>` tags across deltas

**Recommended approach:** Core provides `MemoryContextWrapper` class with `wrap(text) -> str` and `strip(text) -> str`. Plugin calls `wrap()` on prefetch output. Core calls `strip()` before injection. Streaming scrubber lives in core's output pipeline.

### 2.4 `hermes_home` Injection in `initialize()`

**Problem:** The fork's `initialize_all()` injects `hermes_home` into kwargs before calling each provider's `initialize()`. Some providers need to know where `~/.hermes/` is to find config or data files. The plugin doesn't inject this.

**What core needs:**
- Pass `hermes_home` as a kwarg when calling `provider.initialize(session_id, hermes_home=..., ...)`
- This is a one-line change in core's initialization code

**Recommended approach:** Always pass `hermes_home` in the kwargs dict. Providers that don't need it ignore it via `**kwargs`.

### 2.5 Plugin CLI Discovery

**Problem:** The fork scans provider directories for `cli.py` files with `register_cli()` functions, allowing providers to add CLI subcommands (e.g., `hermes memory holographic stats`). The plugin can't register CLI commands — that's a core CLI concern.

**What core needs:**
- After loading memory providers, scan for `cli.py` in provider plugin directories
- Call `register_cli(subparser)` on any found
- OR: add a `cli_commands()` method to the MemoryProvider ABC that returns a list of `(name, help, setup_fn)` tuples

**Recommended approach:** Add `cli_commands()` to the MemoryProvider ABC. Default returns `[]`. The multi-memory plugin can forward CLI commands from sub-providers.

### 2.6 Streaming Output Integration

**Problem:** The fork's `StreamingContextScrubber` intercepts streaming output chunks to handle memory-context tags that span multiple deltas. This is part of the streaming output pipeline in `run_agent.py`. The plugin has no access to this pipeline.

**What core needs:**
- A middleware/interceptor in the streaming output pipeline that the plugin can hook into
- OR: core owns the scrubber and calls `plugin.sanitize_stream_chunk(chunk)` for each delta

**Recommended approach:** Core provides `MemoryStreamScrubber` as a generator/transform. Plugin provides the tag patterns and strip logic. Core applies it in the output pipeline.

---

## 3. Proposed Core Changes (Minimal, Amenable to Plugin)

### 3.1 MemoryProvider ABC Extensions

Add these to the base `MemoryProvider` class:

```python
class MemoryProvider(ABC):
    # Existing methods...

    def cli_commands(self) -> list[tuple[str, str, Callable]]:
        """Return [(name, help_text, setup_fn)] for CLI subcommands.

        setup_fn(subparser) adds arguments and sets defaults.
        Called once at CLI startup.
        Default: no commands.
        """
        return []

    def request_schema_refresh(self) -> bool:
        """Return True if schemas changed and the tool list should be rebuilt.

        Called by core after lifecycle hooks (on_session_switch, etc.)
        to detect dynamic schema changes.
        Default: False (schemas are static).
        """
        return False
```

### 3.2 MemoryManager Changes

```python
class MemoryManager:
    def get_all_tool_schemas(self, *, toolsets_enabled: set = None) -> list[dict]:
        # Filter by toolsets BEFORE calling providers
        if toolsets_enabled is not None and 'memory' not in toolsets_enabled:
            return []
        # Don't cache — always call fresh
        schemas = []
        for provider in self._providers:
            schemas.extend(provider.get_tool_schemas())
        return schemas

    def on_session_switch(self, session_id, **kwargs):
        for provider in self._providers:
            provider.on_session_switch(session_id, **kwargs)
        # Check if any provider needs schema refresh
        if any(p.request_schema_refresh() for p in self._providers):
            self._invalidate_schema_cache()
```

### 3.3 Context Fencing (Core-Owned)

```python
# In agent/context.py or similar

MEMORY_TAG_OPEN = "<memory-context>"
MEMORY_TAG_CLOSE = "</memory-context>"
SYSTEM_NOTE = "[System note: memory context injected by memory provider]"

def wrap_memory_context(text: str) -> str:
    """Wrap memory provider output in fenced block."""
    return f"{MEMORY_TAG_OPEN}\n{SYSTEM_NOTE}\n{text}\n{MEMORY_TAG_CLOSE}"

def strip_memory_context(text: str) -> str:
    """Remove all <memory-context>...</memory-context> blocks."""
    # Handles nested, split, and malformed tags
    ...
```

### 3.4 `hermes_home` Injection

```python
# In agent initialization code
provider.initialize(
    session_id=session_id,
    hermes_home=hermes_home,  # always pass
    **other_kwargs
)
```

---

## 4. What Stays in the Plugin (Not Core's Problem)

Everything below is plugin-internal and core should NOT handle:

- Multi-provider fan-out (plugin iterates `_subs`)
- Circuit breaker / health tracking (plugin's `HealthTracker`)
- Tool budget warnings (plugin's `ToolBudgetWarning`)
- Namespace validation (plugin's `NamespaceValidator`)
- Adapter prefix management (strip+re-add in `adapters.py`)
- Metadata write mode introspection (in `adapters.py`)
- Sync messages introspection (in `adapters.py`)
- Config normalization (plugin's `config.py`)
- Runtime add/remove providers (plugin's `__init__.py`)
- close() vs shutdown() preference (plugin's adapters)

---

## 5. Summary of Core Commits Needed

| # | Change | File | Lines | Difficulty |
|---|---|---|---|---|
| 1 | Add `cli_commands()` to MemoryProvider ABC | `agent/memory_manager.py` or ABC file | ~5 | Trivial |
| 2 | Add `request_schema_refresh()` to MemoryProvider ABC | same | ~5 | Trivial |
| 3 | `toolsets_enabled` check in `get_all_tool_schemas()` | `agent/memory_manager.py` | ~2 | Trivial |
| 4 | Pass `hermes_home` in `initialize()` kwargs | `agent/memory_manager.py` | ~1 | Trivial |
| 5 | Lazy schema evaluation (don't cache) | `agent/memory_manager.py` | ~10 | Easy |
| 6 | `wrap_memory_context()` / `strip_memory_context()` | new `agent/context_fence.py` | ~30 | Moderate |
| 7 | `MemoryStreamScrubber` in output pipeline | `agent/run_agent.py` | ~40 | Moderate |

Total: ~93 lines of core changes. Plugin handles everything else.

---

## 6. Migration Path

1. **Now:** Plugin is fully functional with current MemoryProvider ABC
2. **Core PR #1:** Add `cli_commands()`, `request_schema_refresh()`, `hermes_home` injection, `toolsets_enabled` filter (items 1-4, ~13 lines)
3. **Core PR #2:** Context fencing + streaming scrubber (items 6-7, ~70 lines)
4. **Plugin update:** Implement `cli_commands()` forwarding, call `request_schema_refresh()` after `add_provider()`/`remove_provider()`

No breaking changes to existing providers. The new ABC methods have defaults that preserve current behavior.
