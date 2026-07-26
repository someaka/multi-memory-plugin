"""Config robustness tests - defensive handling of malformed config values.

Consolidated from audit passes 2, 3, 4, 7, 8, 9.
"""

from __future__ import annotations

from unittest import mock

from multi_memory import _normalize_multi_config
from multi_memory.config import _is_disabled, get_enabled_backends


class TestIsDisabledSemantics:
    """_is_disabled must handle all YAML boolean representations correctly."""

    # Empty dict semantics (from second pass)
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
        assert _is_disabled("no") is True

    def test_zero_string_is_disabled(self):
        assert _is_disabled("0") is True

    def test_truthy_string_is_enabled(self):
        assert _is_disabled("yes") is False

    def test_whitespace_string_is_disabled(self):
        assert _is_disabled("   ") is True


class TestIsDisabledCaseInsensitive:
    """_is_disabled must be case-insensitive for string values (from fourth pass)."""

    def test_false_uppercase(self):
        assert _is_disabled("FALSE") is True

    def test_false_mixed_case(self):
        assert _is_disabled("FaLsE") is True

    def test_no_uppercase(self):
        assert _is_disabled("NO") is True

    def test_no_mixed_case(self):
        assert _is_disabled("No") is True

    def test_zero_uppercase(self):
        assert _is_disabled("0") is True

    def test_truthy_uppercase(self):
        assert _is_disabled("YES") is False


class TestIsDisabledOffDisabled:
    """_is_disabled recognizes 'off' and 'disabled' strings (from seventh pass)."""

    def test_off_disabled(self):
        assert _is_disabled("off") is True

    def test_uppercase_off_disabled(self):
        assert _is_disabled("OFF") is True

    def test_mixed_case_off_disabled(self):
        assert _is_disabled("Off") is True

    def test_disabled_string(self):
        assert _is_disabled("disabled") is True

    def test_uppercase_disabled(self):
        assert _is_disabled("DISABLED") is True

    def test_mixed_case_disabled(self):
        assert _is_disabled("Disabled") is True

    def test_off_with_whitespace(self):
        assert _is_disabled("  off  ") is True

    def test_disabled_with_whitespace(self):
        assert _is_disabled("  disabled  ") is True

    def test_on_still_enabled(self):
        assert _is_disabled("on") is False

    def test_enabled_still_enabled(self):
        assert _is_disabled("enabled") is False


class TestIsDisabledFloat:
    """_is_disabled handles float zero correctly (from ninth pass)."""

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
