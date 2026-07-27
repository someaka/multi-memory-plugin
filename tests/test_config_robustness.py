"""Config robustness tests - defensive handling of malformed config values.

Consolidated from audit passes 2, 3, 4, 7, 8, 9.
"""

from __future__ import annotations

from unittest import mock

import pytest

from multi_memory import _normalize_multi_config
from multi_memory.config import _is_disabled, get_enabled_backends


class TestIsDisabled:
    """_is_disabled must handle all YAML boolean representations correctly."""

    @pytest.mark.parametrize(
        "value,expected",
        [
            # Boolean semantics
            (True, False),
            (False, True),
            # None semantics
            (None, True),
            # Integer semantics
            (0, True),
            (1, False),
            # Float semantics
            (0.0, True),
            (-0.0, True),
            (1.0, False),
            (0.5, False),
            (3.14, False),
            # String semantics - disabled values
            ("", True),
            ("false", True),
            ("False", True),
            ("FALSE", True),
            ("FaLsE", True),
            ("no", True),
            ("No", True),
            ("NO", True),
            ("0", True),
            ("off", True),
            ("Off", True),
            ("OFF", True),
            ("disabled", True),
            ("Disabled", True),
            ("DISABLED", True),
            ("   ", True),
            ("  off  ", True),
            ("  disabled  ", True),
            # String semantics - enabled values
            ("yes", False),
            ("YES", False),
            ("on", False),
            ("enabled", False),
            # Dict semantics
            ({}, False),
            ({"api_key": "x"}, False),
        ],
    )
    def test_is_disabled_values(self, value, expected):
        """Parametrized test for all _is_disabled input values."""
        assert _is_disabled(value) is expected


class TestNormalizeMultiConfigNonDictMulti:
    """_normalize_multi_config handles non-dict 'multi' values (from second pass)."""

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


class TestNormalizeMultiConfigUnhashableProviders:
    """_normalize_multi_config filters non-hashable items in providers (from eighth pass)."""

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
    """get_enabled_backends filters non-string items from providers (from eighth pass)."""

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


class TestLoadFullConfigEdgeCases:
    """load_full_config handles edge cases (from third, sixth pass)."""

    def test_returns_dict(self, tmp_path):
        from multi_memory.config import load_full_config

        cfg = tmp_path / "config.yaml"
        cfg.write_text("memory:\n  provider: multi\n")
        with mock.patch("multi_memory.config._get_config_path", return_value=str(cfg)):
            result = load_full_config()
        assert result == {"memory": {"provider": "multi"}}

    def test_missing_file_returns_empty(self, tmp_path):
        from multi_memory.config import load_full_config

        cfg = tmp_path / "nonexistent.yaml"
        with mock.patch("multi_memory.config._get_config_path", return_value=str(cfg)):
            result = load_full_config()
        assert result == {}

    def test_non_dict_yaml_returns_empty(self, tmp_path):
        from multi_memory.config import load_full_config

        cfg = tmp_path / "config.yaml"
        cfg.write_text("[1, 2, 3]")
        with mock.patch("multi_memory.config._get_config_path", return_value=str(cfg)):
            result = load_full_config()
        assert result == {}

    def test_invalid_yaml_returns_empty(self, tmp_path):
        from multi_memory.config import load_full_config

        cfg = tmp_path / "config.yaml"
        cfg.write_text(":bad: yaml: [")
        with mock.patch("multi_memory.config._get_config_path", return_value=str(cfg)):
            result = load_full_config()
        assert result == {}

    def test_generic_exception_returns_empty(self):
        """Unexpected error (not FileNotFoundError/PermissionError/YAMLError) returns {}."""
        from multi_memory import config as cfg_mod

        with mock.patch("builtins.open", side_effect=OSError("unexpected")):
            result = cfg_mod.load_full_config()
        assert result == {}
