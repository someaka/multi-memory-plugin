# Multi-Memory Plugin: Core vs Plugin Boundary

**Goal:** Minimize core changes. Maximize what the plugin owns. Every item below is evaluated on one question: *can the plugin physically do this without access to core internals?*

---

## The Principle

Core owns: **plumbing** (how things flow through the system)
Plugin owns: **policy** (what to do with memory backends)

Core should be a dumb pipe that calls plugin methods at the right moments. The plugin should be a smart manager that decides how to fan out, retry, circuit-break, etc.

---

## What the Plugin Already Owns (100% Plugin Today)

These are all internal to the plugin and require zero core awareness:

| Capability | Why Plugin Can Own It |
|---|---|
| Multi-provider fan-out | Plugin iterates its own `_subs` list |
| Thread safety (RLock + snapshot) | Plugin manages its own concurrency |
| Circuit breaker / health tracking | Plugin's `HealthTracker` — core doesn't need to know |
| Tool budget warnings | Plugin's `ToolBudgetWarning` |
| Namespace validation | Plugin's `validate.py` |
| Backend discovery + loading | Plugin's `discovery.py` + `_try_import` |
| 9 adapter classes with prefix management | Plugin's `adapters.py` |
| Metadata write mode introspection | Plugin detects delegate signatures |
| Sync messages introspection | Plugin detects delegate signatures |
| Runtime add/remove providers | Plugin manages `_subs` list |
| Tool introspection (`get_all_tool_names`, `has_tool`) | Plugin inspects its own schemas |
| Health summary | Plugin's `health_summary()` |
| Config normalization (3 formats) | Plugin's `config.py` |
| close() vs shutdown() preference | Plugin's adapters |
| All 8 lifecycle hooks | Plugin dispatches to subs |
| Holographic double-prefix fix | Plugin adapter logic |
| Silent failure prevention | All exceptions logged at WARNING |

---

## What Truly MUST Be in Core (Plugin Cannot Physically Do These)

### 1. `toolsets_enabled` parameter on `get_tool_schemas()`

**Why plugin can't:** The agent loop has a `toolsets_enabled: set[str]` that controls which tool categories (memory, web, terminal, etc.) are visible to the LLM. The plugin doesn't have this set — it's internal to the agent loop.

**Core change:** Pass `toolsets_enabled` as a parameter. Plugin does the filtering.

```python
# Core (MemoryManager or agent loop)
schemas = provider.get_tool_schemas(toolsets_enabled=toolsets_enabled)

# Plugin
def get_tool_schemas(self, *, toolsets_enabled: set[str] = None) -> list[dict]:
    if toolsets_enabled is not None and 'memory' not in toolsets_enabled:
        return []
    # ... normal schema collection
```

**Lines of core change:** ~3 (add parameter pass-through)

### 2. `hermes_home` in `initialize()` kwargs

**Why plugin can't:** Some backends need to know where `~/.hermes/` is to find config/data files. The plugin doesn't know this path — it's set by the core CLI/agent startup.

**Core change:** Always pass `hermes_home` in the kwargs dict to `initialize()`.

```python
# Core
provider.initialize(session_id=session_id, hermes_home=hermes_home, **other_kwargs)
```

**Lines of core change:** ~1

### 3. Lazy schema evaluation (don't cache tool schemas)

**Why plugin can't:** When the plugin calls `remove_provider()` or `add_provider()`, the tool schema list changes. But the core caches schemas at session start. The plugin can't invalidate a cache it doesn't own.

**Core change:** Don't cache schemas. Call `get_tool_schemas()` fresh each time the agent loop needs the tool list for the LLM.

```python
# Core — instead of caching schemas at session start:
def get_tools_for_llm(self):
    return self.memory_provider.get_tool_schemas(toolsets_enabled=self.toolsets_enabled)
```

**Lines of core change:** ~5 (remove cache, call fresh)

### 4. Strip stale `<memory-context>` blocks from prompt

**Why plugin can't:** The core assembles the prompt from system message + user message + context. Before injecting new memory context, old `<memory-context>` blocks must be stripped. The plugin can't modify the prompt after it's been assembled — it doesn't have access to the message list at assembly time.

**Core change:** Before injecting memory output, strip any existing `<memory-context>` blocks.

```python
# Core — in prompt assembly
import re
MEMORY_CONTEXT_RE = re.compile(r'<memory-context>.*?</memory-context>', re.DOTALL)

def assemble_prompt(messages, memory_context=None):
    # Strip stale memory context
    for msg in messages:
        msg['content'] = MEMORY_CONTEXT_RE.sub('', msg['content']).strip()
    # Inject fresh
    if memory_context:
        messages.append({"role": "system", "content": f"<memory-context>\n{memory_context}\n</memory-context>"})
```

**Lines of core change:** ~8

### 5. Streaming scrubber integration

**Why plugin can't:** When the LLM streams output, memory-context tags can be split across deltas. The core's output pipeline handles streaming — the plugin has no access to it.

**Core change:** Add a hook in the streaming pipeline that the plugin can intercept. OR: core owns a simple scrubber and calls `plugin.scrub_stream_chunk(chunk)`.

```python
# Core — in streaming output loop
class MemoryStreamScrubber:
    """Strip <memory-context> blocks from streaming output."""
    def __init__(self):
        self._buffer = ""
        self._in_context = False

    def process(self, chunk: str) -> str:
        # Track open/close tags across split deltas
        # Return chunk with memory-context blocks removed
        ...

# Usage in streaming pipeline
scrubber = MemoryStreamScrubber()
for chunk in llm_stream:
    cleaned = scrubber.process(chunk)
    yield cleaned
```

**Lines of core change:** ~35 (stateful tag tracking across deltas)

---

## What Could Go Either Way (But Belongs in Plugin)

### Context fencing — wrapping output

The plugin wraps its own prefetch output in `<memory-context>` tags. Core just passes it through.

```python
# Plugin — in prefetch()
def prefetch(self, query, **kwargs):
    raw = ...  # collect from subs
    return f"<memory-context>\n{raw}\n</memory-context>"
```

**Why plugin owns this:** The plugin knows its output format. Core doesn't need to know about memory-context tags — it just injects the string.

### CLI commands

The plugin exposes CLI subcommands via a `cli_commands()` method. Core calls it during CLI setup.

```python
# Plugin
def cli_commands(self):
    return [("holographic-stats", "Show holographic memory stats", setup_fn)]

# Core — in CLI setup
for cmd_name, help_text, setup_fn in provider.cli_commands():
    sub = subparsers.add_parser(cmd_name, help=help_text)
    setup_fn(sub)
```

**Why plugin owns the logic:** The plugin knows what commands its backends support. Core just calls the method.

### `request_schema_refresh()` signal

The plugin tells core "schemas changed, rebuild your tool list." Core owns the cache, plugin owns the signal.

```python
# Plugin — after remove_provider()
def remove_provider(self, name):
    # ... remove logic ...
    self._schemas_dirty = True
    return True

def request_schema_refresh(self) -> bool:
    if self._schemas_dirty:
        self._schemas_dirty = False
        return True
    return False
```

**Why plugin owns the signal:** The plugin knows when schemas changed. Core just checks the signal.

---

## Summary: Core Changes Needed

| # | Change | Lines | Difficulty | What Plugin Does |
|---|---|---|---|---|
| 1 | Pass `toolsets_enabled` to `get_tool_schemas()` | ~3 | Trivial | Filters schemas |
| 2 | Pass `hermes_home` in `initialize()` kwargs | ~1 | Trivial | Uses it in backends |
| 3 | Lazy schema evaluation (don't cache) | ~5 | Easy | Benefits automatically |
| 4 | Strip stale `<memory-context>` from prompt | ~8 | Easy | N/A (core owns prompt) |
| 5 | Streaming scrubber hook | ~35 | Moderate | Could provide scrub logic |

**Total core changes: ~52 lines across 2-3 files.**

Everything else — 20+ capabilities — lives in the plugin.

---

## What the Lead Dev Gets

1. **No more memory backend conflicts** — the plugin handles all multi-provider complexity
2. **No more context injection mess** — the plugin wraps its own output, core just strips stale blocks
3. **Clean separation** — core is a dumb pipe, plugin is a smart manager
4. **Runtime flexibility** — backends can be added/removed without restarting
5. **Observable failures** — all exceptions logged at WARNING level, no silent drops
6. **Backwards compatible** — new ABC methods have default implementations, existing providers unchanged
