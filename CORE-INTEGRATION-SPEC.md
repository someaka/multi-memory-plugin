# Multi-Memory Plugin: Core Integration

## Nothing to Propose Upstream

The upstream MemoryManager has one external provider. It's added at startup, used until shutdown. There's no list to manage, no concurrent writes, no multi-backend complexity.

All of that is the plugin's job. The plugin IS the one provider.

## What the Plugin Handles

Everything related to managing multiple backends:

- Thread safety (RLock for sub-provider list)
- Sub-provider lifecycle (add, remove, shutdown, schema validation)
- Circuit breaker / health tracking
- Tool budget warnings
- Namespace validation / prefix management
- Backend discovery + loading
- Config normalization
- Silent failure prevention (logger.warning)
- Connection pool cleanup (close vs shutdown)
- Adapter-specific fixes (holographic double-prefix, etc.)
- Metadata write mode introspection
- Sync messages introspection

## Fork Features — All Ported

| Fork Feature | Plugin Status |
|---|---|
| Thread safety (RLock) | ✅ |
| `remove_provider()` | ✅ |
| Multi-provider fan-out | ✅ |
| Schema validation before registration | ✅ |
| Namespace validation | ✅ |
| Tool budget warning | ✅ |
| WARNING-level logging | ✅ |
| `toolsets_enabled` filtering | N/A — core handles this at agent level |
| Circuit breaker / health tracking | ✅ (plugin is ahead of fork) |
| close() vs shutdown() | ✅ (plugin is ahead of fork) |
| Metadata write introspection | ✅ |
| Sync messages introspection | ✅ |

## Upstream Is Done

No changes needed. The plugin implements `MemoryProvider`, registers once, and the core calls all lifecycle hooks, tools, and context fencing automatically.
