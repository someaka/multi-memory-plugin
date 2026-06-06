"""Self-contained test configuration — tests work without PYTHONPATH."""

from __future__ import annotations

import os
import sys
from importlib.util import find_spec
from typing import Any

import pytest

# Add src to sys.path so imports work without pip install -e or PYTHONPATH
_src = os.path.join(os.path.dirname(__file__), "..", "src")
if _src not in sys.path:
    sys.path.insert(0, _src)


def _holographic_available() -> bool:
    """Check if the holographic backend is importable.

    Checks the import first.  If PYTHONPATH is set to include the
    hermes-agent source tree (via ``make test`` or CI), the import
    succeeds directly.  Otherwise falls back to checking known
    source locations on disk without modifying sys.path — runtime
    path manipulation inside test collection is too slow.
    """
    try:
        if find_spec("plugins.memory.holographic") is not None:
            return True
    except (ModuleNotFoundError, ValueError):
        pass

    for candidate in (
        os.path.expanduser("~/.hermes/hermes-agent"),
        "/tmp/hermes-agent",
    ):
        p = os.path.join(candidate, "plugins", "memory", "holographic", "__init__.py")
        if os.path.isfile(p):
            return True
    return False


requires_holographic = pytest.mark.skipif(
    not _holographic_available(),
    reason="holographic backend not available (requires Hermes plugins package)",
)


def timeout_wrapper(fn: Any, timeout: float = 30.0) -> Any:
    """Run *fn()* with a wall-clock timeout.  Test utility."""
    from concurrent.futures import ThreadPoolExecutor
    from concurrent.futures import TimeoutError as _FutTimeout

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(fn)
        try:
            return future.result(timeout=timeout)
        except _FutTimeout:
            raise TimeoutError(f"Operation timed out after {timeout}s") from None
