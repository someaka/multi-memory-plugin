"""Lightweight failure tracking for sub-providers.

Each backend has a consecutive failure counter.  Used purely for
status reporting — never used to skip or gate calls.

Thread-safe: all counter mutations are protected by a ``threading.Lock``.
"""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)


class HealthTracker:
    """Per-backend consecutive failure counter for reporting."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # {backend_key: consecutive_failure_count}
        self._counters: dict[str, int] = {}

    def record_success(self, backend_key: str) -> None:
        """Record a successful call — resets the failure counter."""
        with self._lock:
            self._counters.pop(backend_key, None)

    def record_failure(self, backend_key: str) -> None:
        """Record a failed call — increments counter."""
        with self._lock:
            prev = self._counters.get(backend_key, 0)
            self._counters[backend_key] = prev + 1

    def consecutive_failures(self, backend_key: str) -> int:
        """Return the current consecutive failure count (0 = healthy)."""
        with self._lock:
            return self._counters.get(backend_key, 0)

    def reset(self, backend_key: str) -> None:
        """Manually reset a backend to healthy state."""
        with self._lock:
            self._counters.pop(backend_key, None)
