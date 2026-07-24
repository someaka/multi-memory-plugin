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


_state = {"hermes_agent_root": None}


def _hermes_agent_candidates() -> list[str]:
    """Return candidate directories for the hermes-agent source tree.

    Resolution order:
    1. ``HERMES_AGENT_PATH`` env var (explicit override)
    2. ``~/.hermes/hermes-agent`` (default checkout)
    3. ``/tmp/hermes-agent`` (CI)
    """
    candidates: list[str] = []
    env_path = os.environ.get("HERMES_AGENT_PATH", "")
    if env_path:
        candidates.append(os.path.expanduser(env_path))
    candidates.extend(
        [
            os.path.expanduser("~/.hermes/hermes-agent"),
            "/tmp/hermes-agent",
        ]
    )
    return candidates


def _holographic_available() -> bool:
    """Check if the holographic backend is importable.

    First tries a direct import. If the module isn't importable but
    the source files are found on disk, adds the hermes-agent source
    root to sys.path so subsequent imports succeed.

    Hermes plugins (holographic, mem0, etc.) live under
    ``plugins/memory/<name>/`` in the hermes-agent source tree, so
    the source root needs to be on sys.path for ``find_spec`` to
    resolve ``plugins.memory.holographic``.
    """

    try:
        if find_spec("plugins.memory.holographic") is not None:
            return True
    except (ModuleNotFoundError, ValueError):
        pass

    for candidate in _hermes_agent_candidates():
        p = os.path.join(candidate, "plugins", "memory", "holographic", "__init__.py")
        if os.path.isfile(p):
            # Found the source — add it to sys.path so imports work
            if candidate not in sys.path:
                sys.path.insert(0, candidate)
                _state["hermes_agent_root"] = candidate
            return True
    return False


def _ensure_hermes_agent_on_path() -> None:
    """Ensure the hermes-agent source root is on sys.path for all tests.

    Called during pytest_configure so every test has access to the
    bundled memory providers (holographic, mem0, ...) without
    needing PYTHONPATH in the environment.

    Uses the same discovery logic as _holographic_available() for
    consistency.
    """
    if _state["hermes_agent_root"] is not None:
        return

    for candidate in _hermes_agent_candidates():
        p = os.path.join(candidate, "plugins", "memory", "holographic", "__init__.py")
        if os.path.isfile(p):
            if candidate not in sys.path:
                sys.path.insert(0, candidate)
                _state["hermes_agent_root"] = candidate
            return


def pytest_configure(config: pytest.Config) -> None:
    """Add hermes-agent source to sys.path before test collection."""
    _ensure_hermes_agent_on_path()


requires_holographic = pytest.mark.skipif(
    not _holographic_available(),
    reason="holographic backend not available (requires Hermes plugins package)",
)
