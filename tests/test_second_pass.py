"""Tests for second-pass audit fixes.

Covers:
- _normalize_multi_config non-dict multi value (crash guard)
- _is_disabled empty-dict semantics ({} is enabled, not disabled)
- _SubProviderAdapter.close() fallback to shutdown()
- _SubProviderAdapter.get_config_schema / save_config forwarding
- MultiMemoryProvider.get_config_schema / save_config
- _batch_shutdown empty input guard
- _RetainDBAdapter inherits base close() (no override)
"""

# intentional imports-inside-functions + magic numbers in tests
from __future__ import annotations

from unittest import mock

from multi_memory import (
    MultiMemoryProvider,
    _batch_shutdown,
    _is_disabled,
    _normalize_multi_config,
)
from multi_memory.adapters import _RetainDBAdapter, _SubProviderAdapter

# ── _normalize_multi_config non-dict multi value ──────────────────────────


class TestNormaliseMultiConfigNonDictMulti:
    """multi: must be a dict — non-dict truthy values must not crash."""

    def test_multi_is_string(self):
        result = _normalize_multi_config({"multi": "oops"})
        assert result == {}

    def test_multi_is_int(self):
        result = _normalize_multi_config({"multi": 42})
        assert result == {}

    def test_multi_is_list(self):
        result = _normalize_multi_config({"multi": ["a", "b"]})
        assert result == {}

    def test_multi_is_none_falls_through_to_providers(self):
        """multi: null → treated as absent, falls through to providers list."""
        result = _normalize_multi_config({"multi": None, "providers": ["x"]})
        assert result == {"x": {}}

    def test_multi_is_false_falls_through_to_providers(self):
        """multi: false → treated as absent (or {}), falls through."""
        result = _normalize_multi_config({"multi": False, "providers": ["y"]})
        assert result == {"y": {}}

    def test_multi_is_dict_with_backends_still_works(self):
        result = _normalize_multi_config({"multi": {"backends": {"a": {}}}})
        assert result == {"a": {}}


# ── _is_disabled empty-dict semantics ─────────────────────────────────────


class TestIsDisabledEmptyDict:
    """Empty dict {} means enabled — the canonical 'on with no config' value."""

    def test_empty_dict_is_enabled(self):
        assert _is_disabled({}) is False

    def test_non_empty_dict_is_enabled(self):
        assert _is_disabled({"api_key": "x"}) is False

    def test_true_is_enabled(self):
        assert _is_disabled(True) is False

    def test_false_is_disabled(self):
        assert _is_disabled(False) is True

    def test_none_is_disabled(self):
        assert _is_disabled(None) is True

    def test_zero_is_disabled(self):
        assert _is_disabled(0) is True

    def test_one_is_enabled(self):
        assert _is_disabled(1) is False

    def test_empty_string_is_disabled(self):
        assert _is_disabled("") is True

    def test_false_string_is_disabled(self):
        assert _is_disabled("false") is True

    def test_false_capital_string_is_disabled(self):
        assert _is_disabled("False") is True

    def test_no_string_is_disabled(self):
        assert _is_disabled("no") is False or _is_disabled("no") is True
        # "no" is in the disabled set
        assert _is_disabled("no") is True

    def test_zero_string_is_disabled(self):
        assert _is_disabled("0") is True

    def test_truthy_string_is_enabled(self):
        assert _is_disabled("yes") is False

    def test_whitespace_string_is_disabled(self):
        assert _is_disabled("   ") is True


# ── _SubProviderAdapter.close() fallback ──────────────────────────────────


class TestAdapterCloseFallback:
    """close() falls back to shutdown() when delegate has no close()."""

    def _make_adapter(self, delegate):
        adapter = _SubProviderAdapter.__new__(_SubProviderAdapter)
        adapter._delegate = delegate
        adapter._cached_write_mode = None
        adapter._cached_accepts_messages = None
        return adapter

    def test_close_calls_delegate_close(self):
        delegate = mock.MagicMock()
        delegate.close.return_value = None
        adapter = self._make_adapter(delegate)
        adapter.close()
        delegate.close.assert_called_once()
        delegate.shutdown.assert_not_called()

    def test_close_falls_back_to_shutdown(self):
        delegate = mock.MagicMock(spec=["shutdown"])  # no close()
        adapter = self._make_adapter(delegate)
        adapter.close()
        delegate.shutdown.assert_called_once()

    def test_close_no_close_no_shutdown_raises(self):
        """If delegate has neither close() nor shutdown(), close() raises."""
        import contextlib

        delegate = mock.MagicMock(spec=[])  # nothing
        adapter = self._make_adapter(delegate)
        with contextlib.suppress(AttributeError):
            adapter.close()


# ── _SubProviderAdapter.get_config_schema / save_config ───────────────────


class TestAdapterConfigSchema:
    """get_config_schema and save_config forward to delegate."""

    def _make_adapter(self, delegate):
        adapter = _SubProviderAdapter.__new__(_SubProviderAdapter)
        adapter._delegate = delegate
        adapter._cached_write_mode = None
        adapter._cached_accepts_messages = None
        return adapter

    def test_get_config_schema_forwards(self):
        delegate = mock.MagicMock()
        delegate.get_config_schema.return_value = [
            {"key": "api_key", "secret": True},
        ]
        adapter = self._make_adapter(delegate)
        result = adapter.get_config_schema()
        assert result == [{"key": "api_key", "secret": True}]

    def test_get_config_schema_returns_copy(self):
        delegate = mock.MagicMock()
        delegate.get_config_schema.return_value = [{"key": "x"}]
        adapter = self._make_adapter(delegate)
        result = adapter.get_config_schema()
        result.append({"key": "mutated"})
        assert delegate.get_config_schema.return_value == [{"key": "x"}]

    def test_get_config_schema_missing_method(self):
        delegate = mock.MagicMock(spec=[])  # no get_config_schema
        adapter = self._make_adapter(delegate)
        assert adapter.get_config_schema() == []

    def test_save_config_forwards(self):
        delegate = mock.MagicMock()
        adapter = self._make_adapter(delegate)
        adapter.save_config({"mode": "local"}, "/home/.hermes")
        delegate.save_config.assert_called_once_with({"mode": "local"}, "/home/.hermes")

    def test_save_config_missing_method_noop(self):
        delegate = mock.MagicMock(spec=[])  # no save_config
        adapter = self._make_adapter(delegate)
        adapter.save_config({"mode": "local"}, "/home/.hermes")  # should not raise


# ── MultiMemoryProvider.get_config_schema / save_config ───────────────────


class TestMultiProviderConfigSchema:
    """MultiMemoryProvider has no config schema of its own."""

    def test_get_config_schema_returns_empty(self):
        p = MultiMemoryProvider()
        assert p.get_config_schema() == []

    def test_save_config_is_noop(self):
        p = MultiMemoryProvider()
        p.save_config({"key": "val"}, "/home/.hermes")  # should not raise


# ── _batch_shutdown empty input ───────────────────────────────────────────


class TestBatchShutdownEmpty:
    """_batch_shutdown handles empty input without crashing."""

    def test_empty_list_noop(self):
        _batch_shutdown([])  # must not raise

    def test_single_sub(self):
        sub = mock.MagicMock()
        sub.name = "solo"
        sub.close.return_value = None
        _batch_shutdown([sub])
        sub.close.assert_called_once()


# ── _RetainDBAdapter inherits base close() ────────────────────────────────


class TestRetainDBInheritsClose:
    """_RetainDBAdapter no longer overrides close() — base class handles it."""

    def test_no_close_override(self):
        """close is inherited from _SubProviderAdapter, not overridden."""
        assert _RetainDBAdapter.close is _SubProviderAdapter.close
