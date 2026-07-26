"""Tests for error paths and defensive code identified in audit.

This file covers previously untested error paths and defensive checks:
- Schema validation exceptions (lines 319-324 in __init__.py)
- _fan_out non-callable method check (lines 358-363)
- inspect.signature exceptions on on_memory_write and sync_turn (adapters.py)
- Generic backend discovery exceptions (lines 764-765)
- Update command error output (cli.py line 839-841)
- Remove command non-dict guards (cli.py lines 1099-1105)
"""

from __future__ import annotations

import sys
from unittest import mock

from multi_memory import MultiMemoryProvider
from multi_memory.adapters import _SubProviderAdapter


class TestSchemaValidationFailure:
    """__load_config_impl: adapter.get_tool_schemas() raises exception."""

    def test_schema_validation_exception_skips_adapter(self):
        """Adapters that fail schema validation are not registered."""
        provider = MultiMemoryProvider()

        # Create a mock adapter that raises on get_tool_schemas
        broken_adapter = mock.Mock(spec=_SubProviderAdapter)
        broken_adapter.name = "broken"
        broken_adapter.get_tool_schemas.side_effect = RuntimeError("Schema error")

        working_adapter = mock.Mock(spec=_SubProviderAdapter)
        working_adapter.name = "working"
        working_adapter.get_tool_schemas.return_value = [{"name": "tool1", "description": "desc"}]

        # Mock _load_backends_from_config to return both adapters
        with mock.patch("multi_memory._load_backends_from_config") as mock_load:
            mock_load.return_value = [broken_adapter, working_adapter]

            # Trigger config reload
            provider._load_config()

            # Only working adapter should be registered
            assert len(provider._subs) == 1
            assert provider._subs[0].name == "working"


class TestFanOutNonCallable:
    """_fan_out: method exists but is not callable."""

    def test_non_callable_method_skipped(self):
        """Non-callable attributes are skipped with warning."""
        provider = MultiMemoryProvider()

        # Create adapter with non-callable attribute
        adapter = mock.Mock()
        adapter.name = "test"
        adapter.some_method = "not a function"  # Not callable

        provider._subs = [adapter]

        # Should not crash, should skip with warning
        results = provider._fan_out("some_method")
        assert results == []

    def test_missing_method_skipped(self):
        """Missing methods are skipped gracefully."""
        provider = MultiMemoryProvider()

        adapter = mock.Mock(spec=[])  # Empty spec = no methods
        adapter.name = "test"

        provider._subs = [adapter]

        # Should not crash
        results = provider._fan_out("nonexistent_method")
        assert results == []


class TestInspectSignatureExceptions:
    """Adapter introspection: inspect.signature raises TypeError/ValueError."""

    def test_on_memory_write_signature_error_defaults_to_keyword(self):
        """When inspect.signature fails, default to keyword mode."""
        adapter = _SubProviderAdapter.__new__(_SubProviderAdapter)
        adapter._cached_write_mode = None

        # Create delegate with broken signature inspection
        delegate = mock.Mock()
        # Make inspect.signature raise TypeError
        delegate.on_memory_write = object()  # Not inspectable

        adapter._delegate = delegate
        adapter._init_caches()

        # Should default to "keyword" mode
        mode = adapter._metadata_write_mode()
        assert mode == "keyword"

    def test_sync_turn_signature_error_defaults_to_accepts(self):
        """When inspect.signature fails, default to accepting messages."""
        adapter = _SubProviderAdapter.__new__(_SubProviderAdapter)
        adapter._cached_accepts_messages = None

        # Create delegate with broken signature inspection
        delegate = mock.Mock()
        delegate.sync_turn = object()  # Not inspectable

        adapter._delegate = delegate
        adapter._init_caches()

        # Should default to True (accepts messages)
        accepts = adapter._sync_accepts_messages()
        assert accepts is True


class TestGenericBackendDiscoveryException:
    """_try_generic_backend: plugin discovery raises unexpected exception."""

    def test_discovery_exception_logged(self):
        """Unexpected exceptions during plugin discovery are caught and logged."""
        from multi_memory import _try_generic_backend

        backends = []

        # Mock load_memory_provider to raise unexpected exception
        with mock.patch.dict(sys.modules, {"plugins.memory": mock.Mock()}):
            mock_module = sys.modules["plugins.memory"]
            mock_module.load_memory_provider.side_effect = RuntimeError("Discovery failed")

            # Should not crash, should log warning and skip
            _try_generic_backend("custom_backend", backends)

            # Backend should not be added
            assert len(backends) == 0


class TestUpdateCommandErrorOutput:
    """CLI _cmd_update: subprocess returns non-zero with stderr."""

    def test_update_failure_with_stderr(self):
        """Update command shows stderr on failure."""
        import argparse

        from multi_memory.cli import _cmd_update

        args = argparse.Namespace()

        # Mock subprocess to return error with stderr
        mock_result = mock.Mock()
        mock_result.returncode = 1
        mock_result.stderr = "Error: Plugin not found"
        mock_result.stdout = ""

        with (
            mock.patch("subprocess.run", return_value=mock_result),
            mock.patch("builtins.print") as mock_print,
        ):
            _cmd_update(args)

            # Should print error message and stderr
            calls = [str(call) for call in mock_print.call_args_list]
            assert any("Update failed" in call for call in calls)
            assert any("Plugin not found" in call for call in calls)

    def test_update_failure_with_stdout_only(self):
        """Update command shows stdout when stderr is empty."""
        import argparse

        from multi_memory.cli import _cmd_update

        args = argparse.Namespace()

        mock_result = mock.Mock()
        mock_result.returncode = 1
        mock_result.stderr = ""
        mock_result.stdout = "Some output message"

        with (
            mock.patch("subprocess.run", return_value=mock_result),
            mock.patch("builtins.print") as mock_print,
        ):
            _cmd_update(args)

            # Should print stdout as fallback
            calls = [str(call) for call in mock_print.call_args_list]
            assert any("Some output message" in call for call in calls)


class TestRemoveCommandNonDictGuards:
    """CLI _cmd_remove: non-dict multi/backends/providers values."""

    def test_remove_with_non_dict_multi(self):
        """Remove command handles non-dict multi config gracefully."""
        import argparse

        from multi_memory.cli import _cmd_remove

        args = argparse.Namespace(backend="test_backend", force=True)

        # Config with non-dict multi value
        config = {
            "memory": {
                "multi": "not a dict",  # Invalid
                "providers": ["test_backend"],
            }
        }

        with (
            mock.patch("multi_memory.cli.load_config", return_value=config),
            mock.patch("multi_memory.cli.save_config") as mock_save,
            mock.patch("builtins.print"),
        ):
            # Should not crash
            _cmd_remove(args)

            # Should save cleaned config
            assert mock_save.called

    def test_remove_with_non_dict_backends(self):
        """Remove command handles non-dict backends gracefully."""
        import argparse

        from multi_memory.cli import _cmd_remove

        args = argparse.Namespace(backend="test_backend", force=True)

        config = {
            "memory": {
                "multi": {
                    "backends": "not a dict"  # Invalid
                },
                "providers": ["test_backend"],
            }
        }

        with (
            mock.patch("multi_memory.cli.load_config", return_value=config),
            mock.patch("multi_memory.cli.save_config") as mock_save,
            mock.patch("builtins.print"),
        ):
            _cmd_remove(args)
            assert mock_save.called

    def test_remove_with_non_list_providers(self):
        """Remove command handles non-list providers gracefully."""
        import argparse

        from multi_memory.cli import _cmd_remove

        args = argparse.Namespace(backend="test_backend", force=True)

        config = {
            "memory": {
                "multi": {"backends": {"test_backend": {}}},
                "providers": "not a list",  # Invalid
            }
        }

        with (
            mock.patch("multi_memory.cli.load_config", return_value=config),
            mock.patch("multi_memory.cli.save_config") as mock_save,
            mock.patch("builtins.print"),
        ):
            _cmd_remove(args)
            assert mock_save.called
