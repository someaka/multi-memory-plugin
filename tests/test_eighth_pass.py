"""Tests for audit pass 8 — unhashable/non-string items in providers list.

Covers:
- _normalize_multi_config crashes on non-hashable items (list/dict) in providers
- get_enabled_backends passes non-string items through (int, None)
- _get_active_backends passes non-string items through (int, None)
"""

from __future__ import annotations

from multi_memory import _normalize_multi_config
from multi_memory.cli import _get_active_backends
from multi_memory.config import get_enabled_backends


class TestNormalizeMultiConfigUnhashableProviders:
    """_normalize_multi_config must not crash on unhashable items in providers list."""

    def test_providers_with_list_item(self):
        """List item in providers no longer crashes with TypeError."""
        cfg = {"providers": [[1, 2]]}
        result = _normalize_multi_config(cfg)
        assert result == {}

    def test_providers_with_dict_item(self):
        """Dict item in providers no longer crashes with TypeError."""
        cfg = {"providers": [{"key": "val"}]}
        result = _normalize_multi_config(cfg)
        assert result == {}

    def test_providers_with_int_item(self):
        """Int items are not valid backend names — filtered out."""
        cfg = {"providers": [42]}
        result = _normalize_multi_config(cfg)
        assert result == {}

    def test_providers_with_none_item(self):
        """None items filtered out."""
        cfg = {"providers": [None]}
        result = _normalize_multi_config(cfg)
        assert result == {}

    def test_providers_mixed_valid_and_invalid(self):
        """Only string items survive the filter."""
        cfg = {"providers": ["mnemosyne", [1, 2], 42, None, "mem0"]}
        result = _normalize_multi_config(cfg)
        assert "mnemosyne" in result
        assert "mem0" in result
        assert len(result) == 2

    def test_providers_normal_case_unchanged(self):
        """Normal string-only providers list works as before."""
        cfg = {"providers": ["mnemosyne", "mem0"]}
        result = _normalize_multi_config(cfg)
        assert result == {"mnemosyne": {}, "mem0": {}}


class TestGetEnabledBackendsNonStringProviders:
    """get_enabled_backends filters non-string items from providers list."""

    def test_providers_with_int(self):
        cfg = {"providers": [42, "mnemosyne"]}
        result = get_enabled_backends(cfg)
        assert result == ["mnemosyne"]

    def test_providers_with_none(self):
        cfg = {"providers": [None, "mem0"]}
        result = get_enabled_backends(cfg)
        assert result == ["mem0"]

    def test_providers_with_empty_string(self):
        cfg = {"providers": ["", "honcho"]}
        result = get_enabled_backends(cfg)
        assert result == ["honcho"]

    def test_providers_all_non_string(self):
        cfg = {"providers": [42, None, []]}
        result = get_enabled_backends(cfg)
        assert result == []


class TestGetActiveBackendsNonStringProviders:
    """_get_active_backends filters non-string items from providers list."""

    def test_providers_with_int(self):
        cfg = {"providers": [42, "mnemosyne"]}
        result = _get_active_backends(cfg)
        assert result == ["mnemosyne"]

    def test_providers_with_none(self):
        cfg = {"providers": [None, "mem0"]}
        result = _get_active_backends(cfg)
        assert result == ["mem0"]

    def test_providers_with_empty_string(self):
        cfg = {"providers": ["", "honcho"]}
        result = _get_active_backends(cfg)
        assert result == ["honcho"]

    def test_providers_all_non_string(self):
        cfg = {"providers": [42, None]}
        result = _get_active_backends(cfg)
        assert result == []
