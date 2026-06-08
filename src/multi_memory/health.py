"""Circuit-breaker health tracking for sub-providers.

Each backend has a failure counter.  After 3 consecutive failures the
circuit *opens* and the backend is skipped for subsequent lifecycle
calls.  After a cooldown period (30 s) the circuit enters *half-open*
state — one probe call is allowed.  If it succeeds the circuit closes;
if it fails, the circuit re-opens with an extended cooldown.

Thread-safe: all counter mutations are protected by a ``threading.Lock``.
"""

from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────

_CONSECUTIVE_FAILURES_TO_OPEN: int = 3
_HALF_OPEN_COOLDOWN_SECONDS: float = 30.0
_HALF_OPEN_MAX_COOLDOWN: float = 300.0  # 5 min cap on exponential backoff


class HealthTracker:
    """Per-backend circuit breaker with half-open recovery.

    States:
        closed   — healthy, calls pass through
        open     — too many failures, calls are skipped
        half-open — cooldown expired, one probe call allowed
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # {backend_key: consecutive_failure_count}
        self._counters: dict[str, int] = {}
        # {backend_key: timestamp_when_circuit_opened}
        self._opened_at: dict[str, float] = {}
        # {backend_key: current_cooldown_seconds}
        self._cooldown: dict[str, float] = {}

    def record_success(self, backend_key: str) -> None:
        """Record a successful call — resets the failure counter and closes the circuit."""
        with self._lock:
            self._counters.pop(backend_key, None)
            self._opened_at.pop(backend_key, None)
            self._cooldown.pop(backend_key, None)

    def record_failure(self, backend_key: str) -> None:
        """Record a failed call — increments counter, opens circuit at threshold."""
        with self._lock:
            prev = self._counters.get(backend_key, 0)
            new_count = prev + 1
            self._counters[backend_key] = new_count

            if new_count >= _CONSECUTIVE_FAILURES_TO_OPEN:
                was_already_open = backend_key in self._opened_at
                if not was_already_open:
                    logger.warning(
                        "[multi-memory] circuit OPEN for '%s' after %d failures",
                        backend_key,
                        new_count,
                    )
                    self._opened_at[backend_key] = time.monotonic()
                    self._cooldown[backend_key] = _HALF_OPEN_COOLDOWN_SECONDS
                else:
                    # Re-open after half-open probe failure — extend cooldown
                    prev_cooldown = self._cooldown.get(backend_key, _HALF_OPEN_COOLDOWN_SECONDS)
                    self._cooldown[backend_key] = min(prev_cooldown * 2, _HALF_OPEN_MAX_COOLDOWN)
                    self._opened_at[backend_key] = time.monotonic()

    def is_open(self, backend_key: str) -> bool:
        """Return True if the circuit is open (backend should be skipped).

        After the cooldown period, returns False (half-open) to allow
        one probe call.  If the probe fails, ``record_failure`` re-opens
        with an extended cooldown.
        """
        with self._lock:
            opened = self._opened_at.get(backend_key)
            if opened is None:
                return False  # circuit is closed

            cooldown = self._cooldown.get(backend_key, _HALF_OPEN_COOLDOWN_SECONDS)
            elapsed = time.monotonic() - opened
            return elapsed < cooldown  # True = still in cooldown, False = half-open

    def reset(self, backend_key: str) -> None:
        """Manually reset a backend to healthy state."""
        with self._lock:
            self._counters.pop(backend_key, None)
            self._opened_at.pop(backend_key, None)
            self._cooldown.pop(backend_key, None)
