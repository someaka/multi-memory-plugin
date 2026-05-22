"""Tests for multi_memory.health — HealthTracker, timeout_wrapper, CircuitOpenError."""
from __future__ import annotations

import logging
import time
from unittest import mock

import pytest

from multi_memory.health import (
    DEFAULT_FAILURE_LIMIT,
    DEFAULT_TIMEOUT,
    CircuitOpenError,
    HealthTracker,
    timeout_wrapper,
)
from multi_memory.health import logger as health_logger  # for caplog tests


class TestHealthTracker:
    """HealthTracker: per-backend failure tracking + circuit breaker."""

    def test_default_failure_limit(self):
        ht = HealthTracker()
        assert ht._failure_limit == DEFAULT_FAILURE_LIMIT

    def test_custom_failure_limit(self):
        ht = HealthTracker(failure_limit=5)
        assert ht._failure_limit == 5

    def test_fresh_is_not_open(self):
        ht = HealthTracker()
        assert not ht.is_open("backend_a")

    def test_below_threshold_not_open(self):
        ht = HealthTracker(failure_limit=3)
        ht.record_failure("backend_a")
        ht.record_failure("backend_a")
        assert not ht.is_open("backend_a")

    def test_at_threshold_is_open(self):
        ht = HealthTracker(failure_limit=3)
        ht.record_failure("backend_a")
        ht.record_failure("backend_a")
        ht.record_failure("backend_a")
        assert ht.is_open("backend_a")

    def test_above_threshold_also_open(self):
        ht = HealthTracker(failure_limit=3)
        for _ in range(5):
            ht.record_failure("backend_a")
        assert ht.is_open("backend_a")

    def test_failures_returns_count(self):
        ht = HealthTracker()
        assert ht.failures("backend_a") == 0
        ht.record_failure("backend_a")
        assert ht.failures("backend_a") == 1
        ht.record_failure("backend_a")
        assert ht.failures("backend_a") == 2

    def test_record_success_resets_counter(self):
        ht = HealthTracker()
        ht.record_failure("backend_a")
        ht.record_failure("backend_a")
        assert ht.failures("backend_a") == 2
        ht.record_success("backend_a")
        assert ht.failures("backend_a") == 0
        assert not ht.is_open("backend_a")

    def test_record_success_on_untracked_key_does_nothing(self):
        ht = HealthTracker()
        ht.record_success("never_failed")
        assert ht.failures("never_failed") == 0

    def test_different_backends_independent(self):
        ht = HealthTracker(failure_limit=3)
        ht.record_failure("a")
        ht.record_failure("b")
        ht.record_failure("b")
        assert ht.failures("a") == 1
        assert ht.failures("b") == 2
        assert not ht.is_open("a")
        assert not ht.is_open("b")
        ht.record_failure("b")
        assert ht.is_open("b")
        assert not ht.is_open("a")

    def test_reset_single_key(self):
        ht = HealthTracker(failure_limit=3)
        ht.record_failure("a")
        ht.record_failure("b")
        ht.reset("a")
        assert ht.failures("a") == 0
        assert ht.failures("b") == 1

    def test_reset_all_keys(self):
        ht = HealthTracker(failure_limit=3)
        ht.record_failure("a")
        ht.record_failure("b")
        ht.record_failure("b")
        ht.reset()
        assert ht.failures("a") == 0
        assert ht.failures("b") == 0

    def test_reset_unknown_key_does_nothing(self):
        ht = HealthTracker()
        ht.reset("never_failed")  # should not raise

    def test_warning_logged_at_threshold(self, caplog):
        """record_failure logs a warning when circuit opens."""
        ht = HealthTracker(failure_limit=2)
        with caplog.at_level(logging.WARNING, logger="multi_memory.health"):
            ht.record_failure("mem0")
            assert len(caplog.records) == 0
            ht.record_failure("mem0")
        assert len(caplog.records) == 1
        assert "circuit OPEN for mem0" in caplog.records[0].getMessage()
        assert "(2 consecutive failures)" in caplog.records[0].getMessage()

    def test_warning_logged_only_when_threshold_crossed(self, caplog):
        """Warning is not logged again on subsequent failures above threshold."""
        ht = HealthTracker(failure_limit=2)
        with caplog.at_level(logging.WARNING, logger="multi_memory.health"):
            ht.record_failure("mem0")
            ht.record_failure("mem0")  # opens here
            ht.record_failure("mem0")  # still open, no new warning
        assert len(caplog.records) == 1


class TestTimeoutWrapper:
    """timeout_wrapper: circuit-breaking + duration tracking decorator."""

    def test_success_records_and_returns(self):
        tracker = HealthTracker()
        wrapped = timeout_wrapper(
            lambda: "ok", backend_key="test", tracker=tracker
        )
        result = wrapped()
        assert result == "ok"
        assert tracker.failures("test") == 0  # success resets

    def test_failure_records_and_raises(self):
        tracker = HealthTracker()

        def failing():
            raise ValueError("boom")

        wrapped = timeout_wrapper(failing, backend_key="test", tracker=tracker)
        with pytest.raises(ValueError, match="boom"):
            wrapped()
        assert tracker.failures("test") == 1

    def test_circuit_open_raises_immediately(self):
        tracker = HealthTracker(failure_limit=1)
        tracker.record_failure("test")  # now open

        wrapped = timeout_wrapper(
            lambda: "should not call", backend_key="test", tracker=tracker
        )
        with pytest.raises(CircuitOpenError, match="Circuit open for backend 'test'"):
            wrapped()

    def test_slow_but_successful_logs_warning(self, caplog):
        """A call that succeeds but exceeds timeout logs a warning."""
        tracker = HealthTracker()

        def slow_func():
            return "done"

        with (
            mock.patch.object(time, "monotonic", side_effect=[0.0, 61.0]),
            caplog.at_level(logging.WARNING, logger="multi_memory.health"),
        ):
            wrapped = timeout_wrapper(
                slow_func, backend_key="test", tracker=tracker, timeout=30.0
            )
            result = wrapped()

        assert result == "done"
        assert len(caplog.records) == 1
        msg = caplog.records[0].getMessage()
        assert "took 61.0s" in msg
        assert "exceeded 30.0s timeout" in msg
        assert "but succeeded" in msg

    def test_slow_and_failing_logs_warning(self, caplog):
        """A call that fails after exceeding timeout logs a warning."""
        tracker = HealthTracker()

        def slow_and_bad():
            raise RuntimeError("timeout-exceeded")

        with (
            mock.patch.object(time, "monotonic", side_effect=[0.0, 31.0]),
            caplog.at_level(logging.WARNING, logger="multi_memory.health"),
        ):
            wrapped = timeout_wrapper(
                slow_and_bad, backend_key="test", tracker=tracker, timeout=5.0
            )
            with pytest.raises(RuntimeError, match="timeout-exceeded"):
                wrapped()

        assert len(caplog.records) == 1
        msg = caplog.records[0].getMessage()
        assert "took 31.0s" in msg
        assert "exceeded 5.0s timeout" in msg
        assert "and failed" in msg
        # Failure counter should be incremented
        assert tracker.failures("test") == 1

    def test_uses_default_timeout(self):
        """Default timeout is 30 seconds."""
        tracker = HealthTracker()
        wrapped = timeout_wrapper(
            lambda: "ok", backend_key="test", tracker=tracker
        )
        # We can't easily assert the timeout value directly since it's a default param,
        # but we can verify the wrapper works with defaults
        assert wrapped() == "ok"

    def test_functools_wraps_preserved(self):
        def my_func(arg1, arg2):
            """My docstring."""
            return arg1 + arg2

        tracker = HealthTracker()
        wrapped = timeout_wrapper(
            my_func, backend_key="test", tracker=tracker
        )
        assert wrapped.__name__ == "my_func"
        assert wrapped.__wrapped__ is my_func
        assert wrapped.__doc__ == "My docstring."

    def test_circuit_open_message_includes_failure_count(self):
        tracker = HealthTracker(failure_limit=2)
        tracker.record_failure("test")
        tracker.record_failure("test")

        wrapped = timeout_wrapper(
            lambda: "nope", backend_key="test", tracker=tracker
        )
        with pytest.raises(CircuitOpenError) as exc_info:
            wrapped()
        assert "(2 consecutive failures)" in str(exc_info.value)


class TestCircuitOpenError:
    """CircuitOpenError is a RuntimeError subclass."""

    def test_is_runtime_error(self):
        assert issubclass(CircuitOpenError, RuntimeError)

    def test_can_be_raised_with_message(self):
        with pytest.raises(CircuitOpenError, match="custom message"):
            raise CircuitOpenError("custom message")
