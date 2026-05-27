"""Tests for multi_memory.config and config-adjacent functions in __init__.py."""
from __future__ import annotations

from unittest import mock

from multi_memory import _normalise_multi_config, _load_backends_from_config
from multi_memory.config import load_multi_config, get_enabled_backends
from conftest import requires_holographic


class TestNormaliseMultiConfig:
    """Additional edge cases beyond the basic tests in test_adapters."""

    def test_none_cfg(self):
        assert _normalise_multi_config(None) == {}

    def test_providers_list_with_single(self):
        result = _normalise_multi_config({"providers": ["holographic"]})
        assert result == {"holographic": {}}

    def test_both_formats_providers_wins(self):
        """providers list wins over multi.backends when both present."""
        result = _normalise_multi_config({
            "providers": ["holographic"],
            "multi": {"backends": {"mnemosyne": {}}},
        })
        assert result == {"holographic": {}}

    def test_providers_not_a_list(self):
        """providers that isn't a list triggers multi.backends fallback."""
        result = _normalise_multi_config({
            "providers": "not-a-list",
            "multi": {"backends": {"mnemosyne": {}}},
        })
        assert result == {"mnemosyne": {}}

    def test_missing_multi_key(self):
        result = _normalise_multi_config({"memory": {"key": "val"}})
        assert result == {}

    def test_backends_not_a_dict(self):
        result = _normalise_multi_config({
            "multi": {"backends": "not-a-dict"},
        })
        assert result == {}


class TestLoadBackendsFromConfig:
    """Additional edge cases for backend loading."""

    def test_no_memory_key(self):
        result = _load_backends_from_config({})
        assert result == []

    @requires_holographic
    def test_investigation_c_format(self):
        """INVESTIGATION-C canonical: memory.providers list."""
        cfg = {"memory": {"providers": ["holographic"]}}
        result = _load_backends_from_config(cfg)
        # holographic is stdlib-backed, so it should be available
        names = [a.name for a in result]
        assert "holographic" in names

    def test_no_no_backends_false_literal(self):
        """enabled=False explicitly as YAML boolean."""
        cfg = {"memory": {"multi": {"backends": {"holographic": False}}}}
        result = _load_backends_from_config(cfg)
        assert result == []

    def test_enabled_int_zero_str(self):
        """enabled=0 as string literal."""
        cfg = {"memory": {"multi": {"backends": {"holographic": "0"}}}}
        result = _load_backends_from_config(cfg)
        assert result == []

    def test_enabled_no_str(self):
        """'no' also disables."""
        cfg = {"memory": {"multi": {"backends": {"holographic": "no"}}}}
        result = _load_backends_from_config(cfg)
        assert result == []

    @requires_holographic
    def test_enabled_str_true(self):
        """String 'True' should NOT disable (it's truthy)."""
        cfg = {"memory": {"multi": {"backends": {"holographic": "True"}}}}
        result = _load_backends_from_config(cfg)
        names = [a.name for a in result]
        assert "holographic" in names

    @requires_holographic
    def test_enabled_int_1(self):
        """Integer 1 should not be disabled."""
        cfg = {"memory": {"multi": {"backends": {"holographic": 1}}}}
        result = _load_backends_from_config(cfg)
        names = [a.name for a in result]
        assert "holographic" in names


class TestLoadMultiConfig:
    """Tests for config.py load_multi_config()."""

    def test_loads_yaml_from_default_path(self, tmp_path):
        """load_multi_config reads from HERMES_HOME/config.yaml."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("memory:\n  provider: multi\n")
        with mock.patch("multi_memory.config._CONFIG_PATH", str(config_file)):
            result = load_multi_config()
        assert result == {"memory": {"provider": "multi"}}

    def test_load_empty_file(self, tmp_path):
        """Empty config file returns empty dict."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("")
        with mock.patch("multi_memory.config._CONFIG_PATH", str(config_file)):
            result = load_multi_config()
        assert result == {}

    def test_load_missing_file_defaults_to_empty(self, tmp_path):
        """Missing config.yaml returns empty dict."""
        config_file = tmp_path / "config.yaml"  # does not exist
        with mock.patch("multi_memory.config._CONFIG_PATH", str(config_file)):
            result = load_multi_config()
        assert result == {}


class TestGetEnabledBackends:
    """Tests for config.py get_enabled_backends()."""

    def test_with_explicit_config(self):
        """Pass config dict directly."""
        cfg = {"multi": {"backends": {"mnemosyne": True, "mem0": False}}}
        result = get_enabled_backends(cfg)
        assert result == ["mnemosyne"]

    def test_empty_backends(self):
        result = get_enabled_backends({"multi": {"backends": {}}})
        assert result == []

    def test_missing_multi_key(self):
        result = get_enabled_backends({"memory": {}})
        assert result == []

    def test_all_enabled_backends(self):
        cfg = {"multi": {"backends": {"a": True, "b": True, "c": True}}}
        result = get_enabled_backends(cfg)
        assert result == ["a", "b", "c"]

    def test_all_disabled(self):
        cfg = {"multi": {"backends": {"a": False, "b": 0, "c": None}}}
        result = get_enabled_backends(cfg)
        assert result == []
