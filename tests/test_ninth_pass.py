"""Tests for audit pass 9 — float zero disable value.

_is_disabled(0.0) previously returned False because isinstance(0.0, int)
is False. YAML parses "0.0" as a float, so `backends: {mem0: 0.0}` would
not disable mem0. Now isinstance(value, int | float) catches both.
"""

from __future__ import annotations

from multi_memory.config import _is_disabled


class TestIsDisabledFloat:
    """_is_disabled handles float zero correctly."""

    def test_float_zero_disabled(self):
        assert _is_disabled(0.0) is True

    def test_float_zero_zero_disabled(self):
        assert _is_disabled(0.0) is True

    def test_negative_float_zero_disabled(self):
        assert _is_disabled(-0.0) is True

    def test_float_one_enabled(self):
        assert _is_disabled(1.0) is False

    def test_float_half_enabled(self):
        assert _is_disabled(0.5) is False

    def test_float_pi_enabled(self):
        assert _is_disabled(3.14) is False

    def test_int_zero_still_disabled(self):
        """Regression: int 0 still disabled after changing to int | float."""
        assert _is_disabled(0) is True

    def test_int_one_still_enabled(self):
        assert _is_disabled(1) is False

    def test_bool_true_still_enabled(self):
        """Regression: bool True still enabled (bool checked before int|float)."""
        assert _is_disabled(True) is False

    def test_bool_false_still_disabled(self):
        """Regression: bool False still disabled."""
        assert _is_disabled(False) is True
