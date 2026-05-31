# Multi-Memory Plugin: Core Integration

## Nothing to Propose Upstream

The upstream MemoryManager has one external provider. It's added at startup, used until shutdown. There's no list to manage, no concurrent writes, no multi-backend complexity.

All of that is the plugin's job. The plugin IS the one provider.

## What the Plugin Handles

Everything related to managing multiple backends:

- Thread safety (RLock for sub-provider list)
- Sub-provider lifecycle (add, remove, shutdown)
- Circuit breaker / health tracking
- Tool budget warnings
- Namespace validation / prefix management
- Backend discovery + loading
- Config normalization
- Silent failure prevention (logger.warning)
- Connection pool cleanup (close vs shutdown)
- Adapter-specific fixes (holographic double-prefix, etc.)

## Upstream Is Done

No changes needed. The plugin implements `MemoryProvider`, registers once, and the core calls all lifecycle hooks, tools, and context fencing automatically.
