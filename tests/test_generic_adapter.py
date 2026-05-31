"""Tests for _GenericAdapter and custom backend discovery."""

from __future__ import annotations

from unittest import mock

import pytest

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
        # Should not raise
        adapter.initialize(session_id="test-123")

    def test_shutdown(self):
        provider = FakeProvider()
        adapter = _GenericAdapter(provider, "custom_backend")
        # Should not raise
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
        with mock.patch(
            "plugins.memory.load_memory_provider",
            return_value=fake_provider,
        ):
            # Need to mock importlib to make plugins.memory importable
            import sys
            mock_pm = mock.MagicMock()
            mock_pm.load_memory_provider.return_value = fake_provider
            old = sys.modules.get("plugins.memory")
            sys.modules["plugins.memory"] = mock_pm
            try:
                _try_generic_backend("custom_backend", backends)
            finally:
                if old is not None:
                    sys.modules["plugins.memory"] = old
                else:
                    sys.modules.pop("plugins.memory", None)

        assert len(backends) == 1
        assert backends[0].name == "custom_backend"
        assert isinstance(backends[0], _GenericAdapter)

    def test_try_generic_backend_not_found(self):
        """_try_generic_backend warns when provider not found."""
        from multi_memory import _try_generic_backend

        import sys
        mock_pm = mock.MagicMock()
        mock_pm.load_memory_provider.return_value = None
        old = sys.modules.get("plugins.memory")
        sys.modules["plugins.memory"] = mock_pm
        try:
            backends = []
            _try_generic_backend("nonexistent", backends)
        finally:
            if old is not None:
                sys.modules["plugins.memory"] = old
            else:
                sys.modules.pop("plugins.memory", None)

        assert len(backends) == 0

    def test_try_generic_backend_import_error(self):
        """_try_generic_backend handles ImportError in standalone mode."""
        from multi_memory import _try_generic_backend

        import sys
        # Remove plugins.memory from sys.modules to trigger ImportError
        old = sys.modules.pop("plugins.memory", None)
        try:
            backends = []
            _try_generic_backend("custom_backend", backends)
        finally:
            if old is not None:
                sys.modules["plugins.memory"] = old

        assert len(backends) == 0

    def test_try_generic_backend_not_available(self):
        """_try_generic_backend skips providers that report not available."""
        from multi_memory import _try_generic_backend

        class UnavailableProvider(FakeProvider):
            def is_available(self):
                return False

        import sys
        mock_pm = mock.MagicMock()
        mock_pm.load_memory_provider.return_value = UnavailableProvider()
        old = sys.modules.get("plugins.memory")
        sys.modules["plugins.memory"] = mock_pm
        try:
            backends = []
            _try_generic_backend("unavailable_backend", backends)
        finally:
            if old is not None:
                sys.modules["plugins.memory"] = old
            else:
                sys.modules.pop("plugins.memory", None)

        assert len(backends) == 0
