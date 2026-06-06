"""Multi-memory plugin for Hermes Agent.

Entry point for Hermes's memory-provider discovery which scans
``__init__.py`` for ``register_memory_provider`` or ``MemoryProvider``.
"""

import sys
from pathlib import Path

_plugin_root = Path(__file__).resolve().parent
_src = _plugin_root / "src"
for _p in (str(_plugin_root), str(_src)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from multi_memory import MultiMemoryProvider, register  # noqa: E402, F401
