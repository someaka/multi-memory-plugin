"""Tests for _GenericAdapter and custom backend discovery."""

from __future__ import annotations

import sys
from unittest import mock

from multi_memory.adapters import _GenericAdapter


class FakeProvider:
    """A fake MemoryProvider that isn't one of the 9 hardcoded backends."""
    name = "custom_backend"

    def is_available(self):
        return True

    def initialize(self, session_id="", **kwargs):
        pass

    def get_tool_schemas(self):
        return [{"name": "custom_remember", "description": "Store a fact"}]

    def handle_tool_call(self, tool_name, args, **kwargs):
        return f"handled: {tool_name}"

    def shutdown(self):
        pass

    def system_prompt_block(self):
        return "# Custom Memory\nActive."


def _mock_plugins_module(load_memory_provider_fn):
    """Set up sys.modules with a mock plugins.memory module.

    Returns a cleanup function.
    """
    mock_plugins = mock.MagicMock()
    mock_plugins_memory = mock.MagicMock()
    mock_plugins_memory.load_memory_provider = load_memory_provider_fn
    mock_plugins.memory = mock_plugins_memory

    old_plugins = sys.modules.get("plugins")
    old_plugins_memory = sys.modules.get("plugins.memory")
    sys.modules["plugins"] = mock_plugins
    sys.modules["plugins.memory"] = mock_plugins_memory

    def cleanup():
        if old_plugins is not None:
            sys.modules["plugins"] = old_plugins
        else:
            sys.modules.pop("plugins", None)
        if old_plugins_memory is not None:
            sys.modules["plugins.memory"] = old_plugins_memory
        else:
            sys.modules.pop("plugins.memory", None)

    return cleanup


class TestGenericAdapter:
    def test_name(self):
        provider = FakeProvider()
        adapter = _GenericAdapter(provider, "custom_backend")
        assert adapter.name == "custom_backend"

    def test_is_available(self):
        provider = FakeProvider()
        adapter = _GenericAdapter(provider, "custom_backend")
        assert adapter.is_available() is True

    def test_get_tool_schemas_no_prefix(self):
        """Generic adapter does NOT prefix tool names."""
        provider = FakeProvider()
        adapter = _GenericAdapter(provider, "custom_backend")
        schemas = adapter.get_tool_schemas()
        assert schemas == [{"name": "custom_remember", "description": "Store a fact"}]

    def test_handle_tool_call_passthrough(self):
        """Generic adapter passes tool_name through unchanged."""
        provider = FakeProvider()
        adapter = _GenericAdapter(provider, "custom_backend")
        result = adapter.handle_tool_call("custom_remember", {"fact": "test"})
        assert result == "handled: custom_remember"

    def test_initialize(self):
        provider = FakeProvider()
        adapter = _GenericAdapter(provider, "custom_backend")
        adapter.initialize(session_id="test-123")

    def test_shutdown(self):
        provider = FakeProvider()
        adapter = _GenericAdapter(provider, "custom_backend")
        adapter.shutdown()

    def test_system_prompt_block(self):
        provider = FakeProvider()
        adapter = _GenericAdapter(provider, "custom_backend")
        assert "Custom Memory" in adapter.system_prompt_block()


class TestGenericAdapterInMultiMemory:
    """Test that _GenericAdapter works when loaded via _try_generic_backend."""

    def test_try_generic_backend_success(self):
        """_try_generic_backend loads a provider via load_memory_provider."""
        from multi_memory import _try_generic_backend

        fake_provider = FakeProvider()
        backends = []
        cleanup = _mock_plugins_module(lambda name: fake_provider if name == "custom_backend" else None)
        try:
            _try_generic_backend("custom_backend", backends)
        finally:
            cleanup()

        assert len(backends) == 1
        assert backends[0].name == "custom_backend"
        assert isinstance(backends[0], _GenericAdapter)

    def test_try_generic_backend_not_found(self):
        """_try_generic_backend warns when provider not found."""
        from multi_memory import _try_generic_backend

        cleanup = _mock_plugins_module(lambda name: None)
        try:
            backends = []
            _try_generic_backend("nonexistent", backends)
        finally:
            cleanup()

        assert len(backends) == 0

    def test_try_generic_backend_import_error(self):
        """_try_generic_backend handles ImportError in standalone mode."""
        from multi_memory import _try_generic_backend

        # Remove plugins.memory from sys.modules to trigger ImportError
        old_p = sys.modules.pop("plugins", None)
        old_pm = sys.modules.pop("plugins.memory", None)
        try:
            backends = []
            _try_generic_backend("custom_backend", backends)
        finally:
            if old_p is not None:
                sys.modules["plugins"] = old_p
            if old_pm is not None:
                sys.modules["plugins.memory"] = old_pm

        assert len(backends) == 0

    def test_try_generic_backend_not_available(self):
        """_try_generic_backend skips providers that report not available."""
        from multi_memory import _try_generic_backend

        class UnavailableProvider(FakeProvider):
            def is_available(self):
                return False

        cleanup = _mock_plugins_module(lambda name: UnavailableProvider())
        try:
            backends = []
            _try_generic_backend("unavailable_backend", backends)
        finally:
            cleanup()

        assert len(backends) == 0
