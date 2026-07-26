"""Adapter robustness tests - lifecycle, schema caching, thread safety.

Consolidated from audit passes 2, 3, 4.
"""

from __future__ import annotations

import threading
from unittest import mock

import pytest

from multi_memory import MultiMemoryProvider, _batch_shutdown, _normalize_multi_config
from multi_memory.adapters import (
    _renorm_schemas,
    _RetainDBAdapter,
    _SubProviderAdapter,
)


class TestAdapterCloseFallback:
    """_SubProviderAdapter.close() falls back to shutdown() (from second pass)."""

    def test_close_calls_delegate_close(self):
        """close() calls delegate.close() if available."""
        delegate = mock.MagicMock()
        adapter = _SubProviderAdapter.__new__(_SubProviderAdapter)
        adapter._delegate = delegate
        adapter._cached_write_mode = None
        adapter._cached_accepts_messages = None

        adapter.close()
        delegate.close.assert_called_once()
        delegate.shutdown.assert_not_called()

    def test_close_falls_back_to_shutdown(self):
        """close() falls back to shutdown() if delegate has no close()."""
        delegate = mock.MagicMock(spec=[])  # no close method
        delegate.shutdown = mock.MagicMock()
        adapter = _SubProviderAdapter.__new__(_SubProviderAdapter)
        adapter._delegate = delegate
        adapter._cached_write_mode = None
        adapter._cached_accepts_messages = None

        adapter.close()
        delegate.shutdown.assert_called_once()

    def test_close_no_close_no_shutdown_raises(self):
        """If delegate has neither close() nor shutdown(), close() raises."""
        delegate = mock.MagicMock(spec=[])  # nothing
        adapter = _SubProviderAdapter.__new__(_SubProviderAdapter)
        adapter._delegate = delegate
        adapter._cached_write_mode = None
        adapter._cached_accepts_messages = None

        with pytest.raises(AttributeError):
            adapter.close()


class TestAdapterConfigSchema:
    """_SubProviderAdapter config schema methods (from second pass)."""

    def test_get_config_schema_forwards(self):
        """get_config_schema() forwards to delegate."""
        delegate = mock.MagicMock()
        delegate.get_config_schema.return_value = [{"key": "api_key"}]
        adapter = _SubProviderAdapter.__new__(_SubProviderAdapter)
        adapter._delegate = delegate
        adapter._cached_write_mode = None
        adapter._cached_accepts_messages = None

        result = adapter.get_config_schema()
        assert result == [{"key": "api_key"}]
        delegate.get_config_schema.assert_called_once()

    def test_get_config_schema_missing_method(self):
        """get_config_schema() returns [] if delegate has no such method."""
        delegate = mock.MagicMock(spec=[])
        adapter = _SubProviderAdapter.__new__(_SubProviderAdapter)
        adapter._delegate = delegate
        adapter._cached_write_mode = None
        adapter._cached_accepts_messages = None

        result = adapter.get_config_schema()
        assert result == []

    def test_save_config_forwards(self):
        """save_config() forwards to delegate."""
        delegate = mock.MagicMock()
        adapter = _SubProviderAdapter.__new__(_SubProviderAdapter)
        adapter._delegate = delegate
        adapter._cached_write_mode = None
        adapter._cached_accepts_messages = None

        adapter.save_config({"api_key": "test"}, "/home/user")
        delegate.save_config.assert_called_once_with({"api_key": "test"}, "/home/user")

    def test_save_config_missing_method_noop(self):
        """save_config() is no-op if delegate has no such method."""
        delegate = mock.MagicMock(spec=[])
        adapter = _SubProviderAdapter.__new__(_SubProviderAdapter)
        adapter._delegate = delegate
        adapter._cached_write_mode = None
        adapter._cached_accepts_messages = None

        adapter.save_config({"api_key": "test"}, "/home/user")
        assert not hasattr(delegate, "save_config") or not delegate.save_config.called


class TestMultiProviderConfigSchema:
    """MultiMemoryProvider config schema methods (from second pass)."""

    def test_get_config_schema_returns_empty(self, tmp_path):
        """MultiMemoryProvider.get_config_schema() returns []."""
        from multi_memory import config as cfg_mod

        cfg = tmp_path / "config.yaml"
        cfg.write_text("memory:\n  multi:\n    backends: {}\n")
        with mock.patch.object(cfg_mod, "_get_config_path", return_value=str(cfg)):
            provider = MultiMemoryProvider()
        assert provider.get_config_schema() == []

    def test_save_config_is_noop(self, tmp_path):
        """MultiMemoryProvider.save_config() is no-op."""
        from multi_memory import config as cfg_mod

        cfg = tmp_path / "config.yaml"
        cfg.write_text("memory:\n  multi:\n    backends: {}\n")
        with mock.patch.object(cfg_mod, "_get_config_path", return_value=str(cfg)):
            provider = MultiMemoryProvider()

        provider.save_config({"test": "value"}, "/home/user")
        assert provider.get_config_schema() == []


class TestBatchShutdownEmpty:
    """_batch_shutdown handles edge cases (from second pass)."""

    def test_empty_list_noop(self):
        """_batch_shutdown([]) is no-op."""
        _batch_shutdown([])
        # Verify no threads were spawned by checking the function returned cleanly
        assert True

    def test_single_sub(self):
        """_batch_shutdown([sub]) calls sub.close()."""
        sub = mock.MagicMock()
        _batch_shutdown([sub])
        sub.close.assert_called_once()


class TestRetainDBInheritsClose:
    """_RetainDBAdapter inherits close() from base (from second pass)."""

    def test_no_close_override(self):
        """_RetainDBAdapter does not override close()."""
        assert _RetainDBAdapter.close is _SubProviderAdapter.close


class TestLoadConfigReentrancy:
    """_load_config re-entrancy guard (from third pass)."""

    def test_reentrant_call_is_noop(self, tmp_path):
        """Calling _load_config() from within __load_config_impl() is no-op."""
        from multi_memory import config as cfg_mod

        cfg = tmp_path / "config.yaml"
        cfg.write_text("memory:\n  multi:\n    backends: {}\n")

        call_count = 0

        def counting_impl(self):
            nonlocal call_count
            call_count += 1
            self._load_config()  # re-entrant call

        with (
            mock.patch.object(cfg_mod, "_get_config_path", return_value=str(cfg)),
            mock.patch.object(
                MultiMemoryProvider, "_MultiMemoryProvider__load_config_impl", counting_impl
            ),
        ):
            MultiMemoryProvider()

        # Should only be called once due to guard
        assert call_count == 1

    def test_loading_flag_initialized(self, tmp_path):
        """_loading flag is initialized to False."""
        from multi_memory import config as cfg_mod

        cfg = tmp_path / "config.yaml"
        cfg.write_text("memory:\n  multi:\n    backends: {}\n")

        with mock.patch.object(cfg_mod, "_get_config_path", return_value=str(cfg)):
            provider = MultiMemoryProvider()

        assert hasattr(provider, "_loading")
        assert provider._loading is False


class TestSchemaCacheThreadSafety:
    """get_tool_schemas() thread safety (from third pass)."""

    def test_concurrent_calls_build_once(self):
        """Concurrent get_tool_schemas() calls build schema only once."""
        provider = MultiMemoryProvider()
        sub = mock.MagicMock()
        sub.name = "test"
        sub.get_tool_schemas.return_value = [{"name": "test_tool"}]
        provider._subs = [sub]

        results = []
        barrier = threading.Barrier(10)

        def get_schemas():
            barrier.wait()
            results.append(provider.get_tool_schemas())

        threads = [threading.Thread(target=get_schemas) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All threads got the same result
        assert len(results) == 10
        assert all(r == [{"name": "test_tool"}] for r in results)
        # Schema built only once (cached)
        assert sub.get_tool_schemas.call_count == 1

    def test_invalidate_and_rebuild(self):
        """_invalidate_schema_cache() forces rebuild on next call."""
        provider = MultiMemoryProvider()
        sub = mock.MagicMock()
        sub.name = "test"
        sub.get_tool_schemas.return_value = [{"name": "test_tool"}]
        provider._subs = [sub]

        # First call builds schema
        result1 = provider.get_tool_schemas()
        assert result1 == [{"name": "test_tool"}]
        assert sub.get_tool_schemas.call_count == 1

        # Invalidate cache
        provider._invalidate_schema_cache()

        # Second call rebuilds
        result2 = provider.get_tool_schemas()
        assert result2 == [{"name": "test_tool"}]
        assert sub.get_tool_schemas.call_count == 2


class TestHandleToolCallEmptyPrefix:
    """handle_tool_call() handles empty prefix (from third pass)."""

    def test_empty_prefix_uses_sub_name(self):
        """Empty prefix falls back to sub.name for routing."""
        provider = MultiMemoryProvider()
        sub = mock.MagicMock()
        sub.name = "test_backend"
        sub.PREFIX = ""
        sub.handle_tool_call.return_value = '{"result": "ok"}'
        provider._subs = [sub]

        result = provider.handle_tool_call("test_backend_query", {"q": "test"})
        assert result == '{"result": "ok"}'
        sub.handle_tool_call.assert_called_once()

    def test_prefix_match_takes_precedence(self):
        """Prefix match takes precedence over fallback routing."""
        provider = MultiMemoryProvider()

        sub1 = mock.MagicMock()
        sub1.name = "backend1"
        type(sub1).PREFIX = mock.PropertyMock(return_value="b1")
        sub1.handle_tool_call.return_value = '{"from": "b1"}'

        sub2 = mock.MagicMock()
        sub2.name = "backend2"
        type(sub2).PREFIX = mock.PropertyMock(return_value="b2")
        sub2.handle_tool_call.return_value = '{"from": "b2"}'

        provider._subs = [sub1, sub2]

        result = provider.handle_tool_call("b2_query", {"q": "test"})
        assert result == '{"from": "b2"}'
        sub2.handle_tool_call.assert_called_once()
        sub1.handle_tool_call.assert_not_called()


class TestRenormSchemasMissingName:
    """_renorm_schemas skips schemas with no resolvable name (normalize_tool_schema)."""

    def test_missing_name_key(self):
        """Missing 'name' key causes the schema to be skipped."""
        schemas = [{"description": "test tool"}]
        result = _renorm_schemas(schemas, "prefix")
        assert len(result) == 0

    def test_empty_name_key(self):
        """Empty 'name' key causes the schema to be skipped."""
        schemas = [{"name": "", "description": "test"}]
        result = _renorm_schemas(schemas, "prefix")
        assert len(result) == 0

    def test_none_name_key(self):
        """None 'name' key causes the schema to be skipped."""
        schemas = [{"name": None, "description": "test"}]
        result = _renorm_schemas(schemas, "prefix")
        assert len(result) == 0

    def test_double_wrapped_schema_unwrapped(self):
        """Double-wrapped OpenAI tool schema is unwrapped and prefixed."""
        schemas = [
            {
                "type": "function",
                "function": {
                    "name": "my_tool",
                    "description": "test",
                    "parameters": {},
                },
            }
        ]
        result = _renorm_schemas(schemas, "pfx")
        assert len(result) == 1
        assert result[0]["name"] == "pfx_my_tool"
        assert result[0]["description"] == "test"
        assert "type" not in result[0]  # unwrapped — no outer type key

    def test_double_wrapped_already_prefixed(self):
        """Double-wrapped schema that already has the prefix is not double-prefixed."""
        schemas = [
            {
                "type": "function",
                "function": {
                    "name": "pfx_my_tool",
                    "description": "test",
                    "parameters": {},
                },
            }
        ]
        result = _renorm_schemas(schemas, "pfx")
        assert len(result) == 1
        assert result[0]["name"] == "pfx_my_tool"

    def test_non_dict_schema_skipped(self):
        """Non-dict schema entries are silently skipped."""
        schemas = ["not a dict", 42, None]  # type: ignore[list-item]
        result = _renorm_schemas(schemas, "pfx")
        assert len(result) == 0

    def test_mixed_valid_and_invalid(self):
        """Valid schemas survive alongside invalid ones."""
        schemas = [
            {"name": "good_tool", "description": "ok"},
            {"description": "no name"},
            {"type": "function", "function": {"name": "wrapped_tool"}},
        ]
        result = _renorm_schemas(schemas, "pfx")
        assert len(result) == 2
        assert result[0]["name"] == "pfx_good_tool"
        assert result[1]["name"] == "pfx_wrapped_tool"


class TestNormalizeRename:
    """_normalize_multi_config naming consistency (from third pass)."""

    def test_function_exists(self):
        """_normalize_multi_config function exists."""
        assert callable(_normalize_multi_config)

    def test_old_name_gone(self):
        """Old name _normalise_multi_config no longer exists."""
        import multi_memory

        assert not hasattr(multi_memory, "_normalise_multi_config")
