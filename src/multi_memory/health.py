"""Per-backend health tracking with circuit-breaker semantics.

Tracks consecutive failures per backend key and opens the circuit
after a configurable threshold (default 3).  Also provides a
``timeout_wrapper`` decorator for marking a call as failed when it
exceeds a duration limit.
"""

from __future__ import annotations

import functools
import logging
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)

DEFAULT_FAILURE_LIMIT = 3
DEFAULT_TIMEOUT = 30.0

__all__ = ["HealthTracker", "CircuitOpenError", "timeout_wrapper", "DEFAULT_FAILURE_LIMIT", "DEFAULT_TIMEOUT"]


class CircuitOpenError(RuntimeError):
    """Raised when a call is skipped because the circuit is open."""


class HealthTracker:
    """Tracks consecutive failures per backend and opens on threshold.

    Parameters
    ----------
    failure_limit : int
        Consecutive failures before the circuit opens (default 3).
    """

    def __init__(self, failure_limit: int = DEFAULT_FAILURE_LIMIT) -> None:
        self._failure_limit = failure_limit
        self._counters: dict[str, int] = {}

    # ── queries ──────────────────────────────────────────────────────────

    def is_open(self, backend_key: str) -> bool:
        """Return ``True`` if the backend circuit is open (tripped)."""
        return self._counters.get(backend_key, 0) >= self._failure_limit

    def failures(self, backend_key: str) -> int:
        """Return current consecutive-failure count for *backend_key*."""
        return self._counters.get(backend_key, 0)

    # ── recording ────────────────────────────────────────────────────────

    def record_success(self, backend_key: str) -> None:
        """Reset the failure counter on success."""
        self._counters.pop(backend_key, None)

    def record_failure(self, backend_key: str) -> None:
        """Increment the failure counter.

        A warning is logged exactly once — the first time the counter
        reaches (or crosses) *failure_limit*.
        """
        prev = self._counters.get(backend_key, 0)
        self._counters[backend_key] = prev + 1
        current = self._counters[backend_key]
        if prev < self._failure_limit <= current:
            logger.warning(
                "[multi-memory] HealthTracker: circuit OPEN for %s "
                "(%d consecutive failures)",
                backend_key,
                current,
            )

    def reset(self, backend_key: str | None = None) -> None:
        """Reset failure counters.  If *backend_key* is *None*, reset all."""
        if backend_key is None:
            self._counters.clear()
        else:
            self._counters.pop(backend_key, None)


def timeout_wrapper(
    func: Callable[..., Any],
    *,
    backend_key: str,
    tracker: HealthTracker,
    timeout: float = DEFAULT_TIMEOUT,
) -> Callable[..., Any]:
    """Wrap *func* so that it records success/failure on *tracker*.

    If the circuit is open the wrapped function raises
    ``CircuitOpenError`` immediately (no call).  Otherwise it calls
    *func* and records the outcome.  (Actual wall-clock timeout
    enforcement is left to the caller — this wrapper tracks duration
    and logs a warning if *timeout* is exceeded.)
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if tracker.is_open(backend_key):
            raise CircuitOpenError(
                f"Circuit open for backend {backend_key!r} "
                f"({tracker.failures(backend_key)} consecutive failures)"
            )
        start = time.monotonic()
        try:
            result = func(*args, **kwargs)
        except Exception as exc:
            elapsed = time.monotonic() - start
            tracker.record_failure(backend_key)
            if elapsed > timeout:
                logger.warning(
                    "[multi-memory] timeout_wrapper: %s took %.1fs "
                    "(exceeded %.1fs timeout) and failed: %s",
                    backend_key,
                    elapsed,
                    timeout,
                    exc,
                )
            raise
        else:
            elapsed = time.monotonic() - start
            tracker.record_success(backend_key)
            if elapsed > timeout:
                logger.warning(
                    "[multi-memory] timeout_wrapper: %s took %.1fs "
                    "(exceeded %.1fs timeout) but succeeded",
                    backend_key,
                    elapsed,
                    timeout,
                )
            return result

    return wrapper
