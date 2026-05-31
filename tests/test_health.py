"""Tests for multi_memory.health — HealthTracker with half-open recovery + timeout_wrapper."""
from __future__ import annotations

import logging
import time
from unittest import mock

import pytest

from multi_memory.health import (
    _CONSECUTIVE_FAILURES_TO_OPEN,
    _HALF_OPEN_COOLDOWN_SECONDS,
    HealthTracker,
    timeout_wrapper,
)


class TestHealthTracker:
    """HealthTracker: per-backend failure tracking + circuit breaker with half-open recovery."""

    def test_fresh_is_not_open(self):
        ht = HealthTracker()
        assert not ht.is_open("backend_a")

    def test_below_threshold_not_open(self):
        ht = HealthTracker()
        ht.record_failure("backend_a")
        ht.record_failure("backend_a")
        assert not ht.is_open("backend_a")

    def test_at_threshold_is_open(self):
        ht = HealthTracker()
        for _ in range(_CONSECUTIVE_FAILURES_TO_OPEN):
            ht.record_failure("backend_a")
        assert ht.is_open("backend_a")

    def test_above_threshold_also_open(self):
        ht = HealthTracker()
        for _ in range(_CONSECUTIVE_FAILURES_TO_OPEN + 2):
            ht.record_failure("backend_a")
        assert ht.is_open("backend_a")

    def test_record_success_resets_counter(self):
        ht = HealthTracker()
        ht.record_failure("backend_a")
        ht.record_failure("backend_a")
        ht.record_success("backend_a")
        assert not ht.is_open("backend_a")

    def test_record_success_on_untracked_key_does_nothing(self):
        ht = HealthTracker()
        ht.record_success("never_failed")  # should not raise

    def test_different_backends_independent(self):
        ht = HealthTracker()
        ht.record_failure("a")
        for _ in range(_CONSECUTIVE_FAILURES_TO_OPEN):
            ht.record_failure("b")
        assert not ht.is_open("a")
        assert ht.is_open("b")

    def test_reset_single_key(self):
        ht = HealthTracker()
        for _ in range(_CONSECUTIVE_FAILURES_TO_OPEN):
            ht.record_failure("a")
        ht.record_failure("b")
        ht.reset("a")
        assert not ht.is_open("a")
        assert not ht.is_open("b")

    def test_reset_unknown_key_does_nothing(self):
        ht = HealthTracker()
        ht.reset("never_failed")  # should not raise

    def test_warning_logged_at_threshold(self, caplog):
        """record_failure logs a warning when circuit opens."""
        ht = HealthTracker()
        with caplog.at_level(logging.WARNING, logger="multi_memory.health"):
            ht.record_failure("mem0")
            assert len(caplog.records) == 0
            ht.record_failure("mem0")
            ht.record_failure("mem0")  # 3rd failure opens circuit
        assert any("circuit OPEN" in r.getMessage() for r in caplog.records)

    def test_warning_logged_only_when_threshold_crossed(self, caplog):
        """Warning is not logged again on subsequent failures above threshold."""
        ht = HealthTracker()
        with caplog.at_level(logging.WARNING, logger="multi_memory.health"):
            for _ in range(_CONSECUTIVE_FAILURES_TO_OPEN):
                ht.record_failure("mem0")  # opens on last one
            ht.record_failure("mem0")  # still open, no new warning
        open_warnings = [r for r in caplog.records if "circuit OPEN" in r.getMessage()]
        assert len(open_warnings) == 1


class TestHalfOpenRecovery:
    """Circuit breaker half-open state — cooldown then probe."""

    def test_half_open_after_cooldown(self):
        """After cooldown expires, is_open returns False (half-open)."""
        ht = HealthTracker()
        t0 = 1000.0

        # Record failures at t0
        with mock.patch("multi_memory.health.time") as mock_time:
            mock_time.monotonic.return_value = t0
            for _ in range(_CONSECUTIVE_FAILURES_TO_OPEN):
                ht.record_failure("backend")
            assert ht.is_open("backend")  # still in cooldown at t0

            # After cooldown
            mock_time.monotonic.return_value = t0 + _HALF_OPEN_COOLDOWN_SECONDS + 1
            assert not ht.is_open("backend")  # half-open

    def test_probe_success_closes_circuit(self):
        """A success during half-open closes the circuit."""
        ht = HealthTracker()
        t0 = 1000.0

        with mock.patch("multi_memory.health.time") as mock_time:
            mock_time.monotonic.return_value = t0
            for _ in range(_CONSECUTIVE_FAILURES_TO_OPEN):
                ht.record_failure("backend")

            mock_time.monotonic.return_value = t0 + _HALF_OPEN_COOLDOWN_SECONDS + 1
            assert not ht.is_open("backend")  # half-open

        # Probe succeeds — circuit closes
        ht.record_success("backend")
        assert not ht.is_open("backend")  # closed

    def test_probe_failure_reopens_with_extended_cooldown(self):
        """A failure during half-open re-opens with exponential backoff."""
        ht = HealthTracker()
        t0 = 1000.0

        with mock.patch("multi_memory.health.time") as mock_time:
            mock_time.monotonic.return_value = t0
            for _ in range(_CONSECUTIVE_FAILURES_TO_OPEN):
                ht.record_failure("backend")

            # Cooldown expires
            mock_time.monotonic.return_value = t0 + _HALF_OPEN_COOLDOWN_SECONDS + 1
            assert not ht.is_open("backend")  # half-open

        # Probe fails — re-opens
        ht.record_failure("backend")
        assert ht.is_open("backend")  # re-opened

    def test_exponential_backoff_doubles_cooldown(self):
        """Each re-open doubles the cooldown."""
        ht = HealthTracker()
        t0 = 1000.0

        with mock.patch("multi_memory.health.time") as mock_time:
            mock_time.monotonic.return_value = t0

            # First open
            for _ in range(_CONSECUTIVE_FAILURES_TO_OPEN):
                ht.record_failure("backend")

            with ht._lock:
                first_cooldown = ht._cooldown.get("backend", _HALF_OPEN_COOLDOWN_SECONDS)

            # Cooldown expires, probe fails
            mock_time.monotonic.return_value = t0 + first_cooldown + 1
            ht.is_open("backend")  # half-open
            ht.record_failure("backend")  # re-opens

            with ht._lock:
                second_cooldown = ht._cooldown.get("backend")

            assert second_cooldown == first_cooldown * 2


class TestThreadSafety:
    """HealthTracker is thread-safe."""

    def test_concurrent_record_failure(self):
        """Multiple threads recording failures doesn't corrupt state."""
        import threading

        ht = HealthTracker()
        errors = []

        def record_many(key, n):
            try:
                for _ in range(n):
                    ht.record_failure(key)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=record_many, args=("a", 100)) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert ht.is_open("a")  # 1000 failures > threshold


class TestTimeoutWrapper:
    """timeout_wrapper: run with wall-clock timeout."""

    def test_success_returns(self):
        result = timeout_wrapper(lambda: "ok", timeout=5.0)
        assert result == "ok"

    def test_timeout_raises(self):
        def slow():
            import time
            time.sleep(100)

        with pytest.raises(TimeoutError):
            timeout_wrapper(slow, timeout=0.01)
