"""Additional test classes appended to test_adapters.py via write_file.

These cover previously untested paths:
- _metadata_write_mode / _sync_accepts_messages edge cases
- _load_via_discovery error handling
- _try_generic_backend error paths
- format_config_display both shapes
- Circuit breaker is_open in _fan_out / get_tool_schemas
- _load_config error paths
- health_summary + __repr__
"""

from __future__ import annotations

from unittest import mock


class TestMetadataWriteMode:
    """_metadata_write_mode() detects delegate signature."""

    def _make_adapter(self, delegate):
        from multi_memory.adapters import _SubProviderAdapter

        class TestAdapter(_SubProviderAdapter):
            CONFIG_KEY = "test"
            PREFIX = "test"

        adapter = TestAdapter.__new__(TestAdapter)
        adapter._delegate = delegate
        adapter._cached_write_mode = None
        adapter._cached_accepts_messages = None
        return adapter

    def test_keyword_mode_with_metadata_param(self):
        delegate = mock.MagicMock()
        import inspect

        sig = inspect.Signature(
            [
                inspect.Parameter("action", inspect.Parameter.POSITIONAL_OR_KEYWORD),
                inspect.Parameter("target", inspect.Parameter.POSITIONAL_OR_KEYWORD),
                inspect.Parameter("content", inspect.Parameter.POSITIONAL_OR_KEYWORD),
                inspect.Parameter("metadata", inspect.Parameter.KEYWORD_ONLY, default=None),
            ]
        )
        adapter = self._make_adapter(delegate)
        with mock.patch("inspect.signature", return_value=sig):
            mode = adapter._metadata_write_mode()
        assert mode == "keyword"

    def test_keyword_mode_with_var_keyword(self):
        delegate = mock.MagicMock()
        import inspect

        sig = inspect.Signature(
            [
                inspect.Parameter("action", inspect.Parameter.POSITIONAL_OR_KEYWORD),
                inspect.Parameter("target", inspect.Parameter.POSITIONAL_OR_KEYWORD),
                inspect.Parameter("content", inspect.Parameter.POSITIONAL_OR_KEYWORD),
                inspect.Parameter("kwargs", inspect.Parameter.VAR_KEYWORD),
            ]
        )
        adapter = self._make_adapter(delegate)
        with mock.patch("inspect.signature", return_value=sig):
            mode = adapter._metadata_write_mode()
        assert mode == "keyword"

    def test_positional_mode_with_4_non_metadata_params(self):
        delegate = mock.MagicMock()
        import inspect

        sig = inspect.Signature(
            [
                inspect.Parameter("action", inspect.Parameter.POSITIONAL_OR_KEYWORD),
                inspect.Parameter("target", inspect.Parameter.POSITIONAL_OR_KEYWORD),
                inspect.Parameter("content", inspect.Parameter.POSITIONAL_OR_KEYWORD),
                inspect.Parameter("extra", inspect.Parameter.POSITIONAL_OR_KEYWORD),
            ]
        )
        adapter = self._make_adapter(delegate)
        with mock.patch("inspect.signature", return_value=sig):
            mode = adapter._metadata_write_mode()
        assert mode == "positional"

    def test_legacy_mode_with_3_params(self):
        delegate = mock.MagicMock()
        import inspect

        sig = inspect.Signature(
            [
                inspect.Parameter("action", inspect.Parameter.POSITIONAL_OR_KEYWORD),
                inspect.Parameter("target", inspect.Parameter.POSITIONAL_OR_KEYWORD),
                inspect.Parameter("content", inspect.Parameter.POSITIONAL_OR_KEYWORD),
            ]
        )
        adapter = self._make_adapter(delegate)
        with mock.patch("inspect.signature", return_value=sig):
            mode = adapter._metadata_write_mode()
        assert mode == "legacy"

    def test_cached_mode_reused(self):
        delegate = mock.MagicMock()
        adapter = self._make_adapter(delegate)
        adapter._cached_write_mode = "positional"
        mode = adapter._metadata_write_mode()
        assert mode == "positional"


class TestSyncAcceptsMessages:
    """_sync_accepts_messages() detects delegate signature."""

    def _make_adapter(self, delegate):
        from multi_memory.adapters import _SubProviderAdapter

        class TestAdapter(_SubProviderAdapter):
            CONFIG_KEY = "test"
            PREFIX = "test"

        adapter = TestAdapter.__new__(TestAdapter)
        adapter._delegate = delegate
        adapter._cached_write_mode = None
        adapter._cached_accepts_messages = None
        return adapter

    def test_var_keyword_accepts(self):
        delegate = mock.MagicMock()
        import inspect

        sig = inspect.Signature(
            [
                inspect.Parameter("user", inspect.Parameter.POSITIONAL_OR_KEYWORD),
                inspect.Parameter("assistant", inspect.Parameter.POSITIONAL_OR_KEYWORD),
                inspect.Parameter("kwargs", inspect.Parameter.VAR_KEYWORD),
            ]
        )
        adapter = self._make_adapter(delegate)
        with mock.patch("inspect.signature", return_value=sig):
            assert adapter._sync_accepts_messages() is True

    def test_messages_kwarg_accepts(self):
        delegate = mock.MagicMock()
        import inspect

        sig = inspect.Signature(
            [
                inspect.Parameter("user", inspect.Parameter.POSITIONAL_OR_KEYWORD),
                inspect.Parameter("assistant", inspect.Parameter.POSITIONAL_OR_KEYWORD),
                inspect.Parameter("messages", inspect.Parameter.KEYWORD_ONLY, default=None),
            ]
        )
        adapter = self._make_adapter(delegate)
        with mock.patch("inspect.signature", return_value=sig):
            assert adapter._sync_accepts_messages() is True

    def test_no_messages_kwarg(self):
        delegate = mock.MagicMock()
        import inspect

        sig = inspect.Signature(
            [
                inspect.Parameter("user", inspect.Parameter.POSITIONAL_OR_KEYWORD),
                inspect.Parameter("assistant", inspect.Parameter.POSITIONAL_OR_KEYWORD),
            ]
        )
        adapter = self._make_adapter(delegate)
        with mock.patch("inspect.signature", return_value=sig):
            assert adapter._sync_accepts_messages() is False

    def test_cached_reused(self):
        delegate = mock.MagicMock()
        adapter = self._make_adapter(delegate)
        adapter._cached_accepts_messages = False
        assert adapter._sync_accepts_messages() is False


class TestLoadViaDiscovery:
    """_load_via_discovery handles errors from load_memory_provider."""

    def test_provider_raises_exception(self):
        import sys

        class MockModule:
            @staticmethod
            def load_memory_provider(name):
                raise RuntimeError("fake crash")

        old = sys.modules.get("plugins.memory")
        sys.modules["plugins.memory"] = MockModule()
        try:
            from multi_memory.adapters import _MnemosyneAdapter

            result = _MnemosyneAdapter._load_via_discovery()
        finally:
            if old is not None:
                sys.modules["plugins.memory"] = old
            else:
                sys.modules.pop("plugins.memory", None)
        assert result is None


class TestTryGenericBackend:
    """_try_generic_backend error paths."""

    def test_plugins_memory_not_importable(self):
        import sys
        from multi_memory import _try_generic_backend

        old = sys.modules.get("plugins.memory")
        sys.modules["plugins.memory"] = None
        try:
            backends = []
            _try_generic_backend("test", backends)
        finally:
            if old is not None:
                sys.modules["plugins.memory"] = old
            else:
                sys.modules.pop("plugins.memory", None)
        assert backends == []


class TestFormatConfigDisplay:
    """format_config_display for both config shapes."""

    def test_backends_dict_format(self):
        from multi_memory import MultiMemoryProvider

        p = MultiMemoryProvider()
        result = p.format_config_display({"multi": {"backends": {"mnemosyne": {}, "mem0": {}}}})
        assert len(result) == 1
        assert result[0][0] == "backends"
        assert "mnemosyne" in result[0][1]
        assert "mem0" in result[0][1]

    def test_providers_list_format(self):
        from multi_memory import MultiMemoryProvider

        p = MultiMemoryProvider()
        result = p.format_config_display({"providers": ["mnemosyne", "mem0"]})
        assert len(result) == 1
        assert result[0][0] == "providers"
        assert "mnemosyne" in result[0][1]

    def test_empty_config(self):
        from multi_memory import MultiMemoryProvider

        p = MultiMemoryProvider()
        result = p.format_config_display({})
        assert result == []


class TestCircuitBreakerInLoop:
    """is_open() checked in _fan_out and get_tool_schemas."""

    def test_fan_out_skips_open_circuit(self):
        from multi_memory import MultiMemoryProvider
        from multi_memory.adapters import _SubProviderAdapter

        p = MultiMemoryProvider()
        p._subs = []
        sub = mock.MagicMock(spec=_SubProviderAdapter)
        sub.name = "test"
        sub.is_available.return_value = True
        p._subs.append(sub)
        p._health._opened_at["test"] = 999999999.0
        results = p._fan_out("system_prompt_block")
        assert results == []

    def test_get_tool_schemas_skips_open_circuit(self):
        from multi_memory import MultiMemoryProvider
        from multi_memory.adapters import _SubProviderAdapter

        p = MultiMemoryProvider()
        p._subs = []
        sub = mock.MagicMock(spec=_SubProviderAdapter)
        sub.name = "test"
        sub.is_available.return_value = True
        sub.get_tool_schemas.return_value = [{"name": "test_tool"}]
        p._subs.append(sub)
        p._health._opened_at["test"] = 999999999.0
        schemas = p.get_tool_schemas()
        assert schemas == []


class TestLoadConfigErrorPaths:
    """_load_config warning/error paths."""

    def test_config_not_a_dict_loads_empty(self, tmp_path):
        from multi_memory import MultiMemoryProvider

        cfg = tmp_path / "config.yaml"
        cfg.write_text("[1, 2, 3]")
        p = MultiMemoryProvider()
        p._subs = []
        with mock.patch("multi_memory.config._get_config_path", return_value=str(cfg)):
            p._load_config()
        assert p._subs == []


class TestHealthSummaryAndRepr:
    """health_summary and __repr__ return values."""

    def test_health_summary(self):
        from multi_memory import MultiMemoryProvider
        from multi_memory.adapters import _SubProviderAdapter

        p = MultiMemoryProvider()
        p._subs = []
        sub = mock.MagicMock(spec=_SubProviderAdapter)
        sub.name = "test"
        p._subs.append(sub)
        summary = p.health_summary()
        assert summary == {"test": "ok"}

    def test_repr(self):
        from multi_memory import MultiMemoryProvider

        p = MultiMemoryProvider()
        p._subs = []
        r = repr(p)
        assert "MultiMemoryProvider" in r
