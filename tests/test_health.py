"""Tests for multi_memory.health — thin failure counter."""

from __future__ import annotations

import threading

from multi_memory.health import HealthTracker


class TestHealthTracker:
    """HealthTracker: per-backend consecutive failure tracking."""

    def test_fresh_has_zero_failures(self):
        ht = HealthTracker()
        assert ht.consecutive_failures("backend_a") == 0

    def test_record_failure_increments(self):
        ht = HealthTracker()
        ht.record_failure("backend_a")
        assert ht.consecutive_failures("backend_a") == 1
        ht.record_failure("backend_a")
        assert ht.consecutive_failures("backend_a") == 2  # noqa: PLR2004

    def test_record_success_resets_counter(self):
        ht = HealthTracker()
        ht.record_failure("backend_a")
        ht.record_failure("backend_a")
        ht.record_success("backend_a")
        assert ht.consecutive_failures("backend_a") == 0

    def test_record_success_on_untracked_key_does_nothing(self):
        ht = HealthTracker()
        ht.record_success("never_failed")  # should not raise

    def test_different_backends_independent(self):
        ht = HealthTracker()
        ht.record_failure("a")
        ht.record_failure("b")
        ht.record_failure("b")
        assert ht.consecutive_failures("a") == 1
        assert ht.consecutive_failures("b") == 2  # noqa: PLR2004

    def test_reset_single_key(self):
        ht = HealthTracker()
        ht.record_failure("a")
        ht.record_failure("b")
        ht.reset("a")
        assert ht.consecutive_failures("a") == 0
        assert ht.consecutive_failures("b") == 1

    def test_reset_unknown_key_does_nothing(self):
        ht = HealthTracker()
        ht.reset("never_failed")  # should not raise


class TestThreadSafety:
    """HealthTracker is thread-safe."""

    def test_concurrent_record_failure(self):
        """Multiple threads recording failures doesn't corrupt state."""
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
        assert ht.consecutive_failures("a") == 1000  # 10 threads × 100 each  # noqa: PLR2004
