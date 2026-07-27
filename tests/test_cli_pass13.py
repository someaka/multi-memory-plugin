"""Tests for cli.py uncovered lines (pass 13)."""

import argparse
from unittest import mock

from multi_memory.cli import (
    _cmd_list,
    _print_legacy_provider_config,
)


class TestPrintLegacyProviderConfig:
    """Test _print_legacy_provider_config edge cases."""

    def test_early_return_empty_config(self, capsys):
        """Line 1022: early return when top_config is empty dict."""
        _print_legacy_provider_config("test_provider", {}, [])
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_early_return_non_dict_config(self, capsys):
        """Line 1022: early return when top_config is not a dict."""
        memory_cfg = {"test_provider": "not_a_dict"}
        _print_legacy_provider_config("test_provider", memory_cfg, [])
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_else_branch_no_get_status_config(self, capsys):
        """Lines 1031-1032: else branch when provider lacks get_status_config."""
        # Create a provider without get_status_config method
        provider_obj = mock.MagicMock(spec=[])  # Empty spec = no methods
        backends_cache = [("test_provider", "desc", provider_obj)]

        memory_cfg = {"test_provider": {"key1": "value1", "key2": "value2"}}
        _print_legacy_provider_config("test_provider", memory_cfg, backends_cache)

        captured = capsys.readouterr()
        assert "test_provider" in captured.out
        assert "key1: value1" in captured.out
        assert "key2: value2" in captured.out


class TestCmdListNonDictMemory:
    """Test _cmd_list with non-dict memory config."""

    @mock.patch("multi_memory.cli.load_config")
    @mock.patch("multi_memory.cli.get_enabled_backends")
    @mock.patch("multi_memory.cli.ALL_BACKENDS", {"test_backend": "Test desc"})
    @mock.patch("multi_memory.cli.BACKEND_CATEGORIES", {"Local": ["test_backend"]})
    def test_cmd_list_non_dict_memory_config(self, mock_get_enabled, mock_load_config, capsys):
        """Line 1153: memory config is non-dict, should coerce to {}."""
        # Config with non-dict memory value
        mock_load_config.return_value = {"memory": "not_a_dict"}
        mock_get_enabled.return_value = []

        args = argparse.Namespace(json_output=False, show_all=False)
        _cmd_list(args)

        # Should not crash and should call get_enabled_backends with {}
        mock_get_enabled.assert_called_once_with({})
