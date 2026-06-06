"""Multi-memory plugin for Hermes Agent — entry point for plugin discovery.

The plugin source lives in ``src/multi_memory/``.  This file re-exports
the MemoryProvider and register() function so that Hermes's memory-provider
discovery (which scans ``__init__.py`` for ``register_memory_provider`` or
``MemoryProvider``) can find and load the provider.
"""

from src.multi_memory import MultiMemoryProvider, register  # noqa: F401

# Reference to satisfy _is_memory_provider_dir heuristic scan
_MemoryProvider = MultiMemoryProvider
