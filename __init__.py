"""Multi-memory plugin for Hermes Agent.

Entry point for Hermes's memory-provider discovery which scans
``__init__.py`` for ``register_memory_provider`` or ``MemoryProvider``.
"""

import sys
from pathlib import Path

# Ensure the plugin root is on sys.path so ``from src.multi_memory`` works
_plugin_root = Path(__file__).resolve().parent
if str(_plugin_root) not in sys.path:
    sys.path.insert(0, str(_plugin_root))

from src.multi_memory import MultiMemoryProvider, register  # noqa: E402, F401
