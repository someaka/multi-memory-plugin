"""Self-contained test configuration — tests work without PYTHONPATH."""
from __future__ import annotations

import os
import sys
from importlib.util import find_spec

import pytest

# Add src to sys.path so imports work without pip install -e or PYTHONPATH
_src = os.path.join(os.path.dirname(__file__), "..", "src")
if _src not in sys.path:
    sys.path.insert(0, _src)


def _holographic_available() -> bool:
    """Check if the holographic backend is importable."""
    try:
        return find_spec("plugins.memory.holographic") is not None
    except (ModuleNotFoundError, ValueError):
        return False


requires_holographic = pytest.mark.skipif(
    not _holographic_available(),
    reason="holographic backend not available (requires Hermes plugins package)",
)
