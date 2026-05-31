# Multi-Memory Plugin: What to Propose Upstream

## Context

The upstream MemoryManager allows one external provider. This is deliberate. The multi-memory plugin is that one provider. It manages multiple backends internally — thread safety, circuit breaker, health tracking, namespace validation are all plugin-internal concerns.

## Proposals (if worth making at all)

### 1. `remove_provider()` (~25 lines)

You can `add_provider()` but never remove. For long-running agents (gateway, cron), hot-swapping a provider requires a restart.

This is genuinely useful for any provider, not just the plugin.

### 2. `logger.debug` → `logger.warning` in lifecycle hooks (~10 lines)

The core swallows provider exceptions at debug level. If Honcho or Mem0 fails, nobody knows unless debug logging is on.

This benefits every provider.

## Not Proposing

- **Thread safety (RLock)** — no race condition with one provider. The plugin manages its own lock internally for sub-providers. Not upstream's problem.
- **Multi-provider support** — the one-provider limit is the design. The plugin exists because of it.

## Summary

| Item | Lines | Upstream Benefit |
|---|---|---|
| `remove_provider()` | ~25 | Any long-running agent |
| Log levels debug→warning | ~10 | Any provider |
