"""Tests for sixth-pass audit: deep isinstance guards on malformed YAML.

Covers:
- get_status_config with non-dict provider_config/multi_cfg/backends/providers
- _get_active_backends with non-dict memory_cfg input
- _cmd_status with non-dict memory_cfg from config.get('memory')
- _cmd_add with pre-existing non-dict 'memory'/'multi'/'backends'/'providers'
- _install_dependencies with non-dict meta from yaml.safe_load
- _install_dependencies with non-dict ext_deps items
- _cmd_add providers_list guard against non-list
"""

from __future__ import annotations

import argparse
from unittest import mock

# ── get_status_config guards ─────────────────────────────────────────────


class TestGetStatusConfigGuards:
    """get_status_config must handle non-dict inputs at every level."""

    def test_non_dict_provider_config_returns_empty(self):
        from multi_memory import MultiMemoryProvider

        result = MultiMemoryProvider.get_status_config(None, "not a dict")  # type: ignore[arg-type]
        assert result == {}

    def test_non_dict_multi_returns_providers(self):
        from multi_memory import MultiMemoryProvider

        result = MultiMemoryProvider.get_status_config(
            None, {"multi": "string", "providers": ["mem0"]}
        )
        assert result == {"providers": "mem0"}

    def test_non_dict_backends_skips(self):
        from multi_memory import MultiMemoryProvider

        result = MultiMemoryProvider.get_status_config(None, {"multi": {"backends": "invalid"}})
        assert result == {}

    def test_non_dict_backends_falls_through_to_providers(self):
        from multi_memory import MultiMemoryProvider

        result = MultiMemoryProvider.get_status_config(
            None,
            {"multi": {"backends": 42}, "providers": ["holographic"]},
        )
        assert result == {"providers": "holographic"}

    def test_non_list_providers_returns_empty(self):
        from multi_memory import MultiMemoryProvider

        result = MultiMemoryProvider.get_status_config(
            None, {"multi": {}, "providers": "not-a-list"}
        )
        assert result == {}

    def test_providers_with_non_string_items(self):
        """Providers list with non-string items should coerce to str."""
        from multi_memory import MultiMemoryProvider

        result = MultiMemoryProvider.get_status_config(
            None, {"providers": [42, None, "holographic"]}
        )
        assert "42" in result["providers"]
        assert "None" in result["providers"]
        assert "holographic" in result["providers"]


# ── _get_active_backends guard ───────────────────────────────────────────


class TestGetActiveBackendsNonDict:
    """_get_active_backends must return [] for non-dict input."""

    def test_none_input(self):
        from multi_memory.cli import _get_active_backends

        assert _get_active_backends(None) == []  # type: ignore[arg-type]

    def test_string_input(self):
        from multi_memory.cli import _get_active_backends

        assert _get_active_backends("not a dict") == []  # type: ignore[arg-type]

    def test_list_input(self):
        from multi_memory.cli import _get_active_backends

        assert _get_active_backends(["a", "b"]) == []  # type: ignore[arg-type]

    def test_int_input(self):
        from multi_memory.cli import _get_active_backends

        assert _get_active_backends(42) == []  # type: ignore[arg-type]


# ── _cmd_status non-dict memory_cfg ──────────────────────────────────────


class TestCmdStatusNonDictMemory:
    """_cmd_status must coerce non-dict memory_cfg to empty dict."""

    def test_status_with_non_dict_memory(self, capsys):
        from multi_memory.cli import _cmd_status

        args = argparse.Namespace(json_output=False, multi_command="status")
        with (
            mock.patch("multi_memory.cli.load_config", return_value={"memory": "corrupt"}),
            mock.patch("multi_memory.cli._get_available_backends", return_value=[]),
        ):
            _cmd_status(args)
        out = capsys.readouterr().out
        assert "Memory status" in out
        assert "built-in only" in out.lower()


# ── _cmd_add non-dict config values ──────────────────────────────────────


class TestCmdAddNonDictGuards:
    """_cmd_add must handle pre-existing non-dict values in config."""

    def test_add_with_non_dict_memory(self, capsys):
        """Pre-existing non-dict 'memory' value must be coerced."""
        from multi_memory.cli import _cmd_add

        args = argparse.Namespace(backend="holographic", multi_command="add")
        captured = {}

        def fake_save(cfg):
            captured["cfg"] = cfg

        with (
            mock.patch("multi_memory.cli.load_config", return_value={"memory": "corrupt"}),
            mock.patch("multi_memory.cli.save_config", side_effect=fake_save),
        ):
            _cmd_add(args)

        out = capsys.readouterr().out
        assert "Added" in out
        assert isinstance(captured["cfg"]["memory"], dict)
        assert captured["cfg"]["memory"]["provider"] == "multi"

    def test_add_with_non_dict_multi(self, capsys):
        from multi_memory.cli import _cmd_add

        args = argparse.Namespace(backend="holographic", multi_command="add")
        captured = {}

        def fake_save(cfg):
            captured["cfg"] = cfg

        with (
            mock.patch(
                "multi_memory.cli.load_config",
                return_value={"memory": {"multi": "corrupt"}},
            ),
            mock.patch("multi_memory.cli.save_config", side_effect=fake_save),
        ):
            _cmd_add(args)

        out = capsys.readouterr().out
        assert "Added" in out
        assert isinstance(captured["cfg"]["memory"]["multi"], dict)

    def test_add_with_non_dict_backends(self, capsys):
        from multi_memory.cli import _cmd_add

        args = argparse.Namespace(backend="holographic", multi_command="add")
        captured = {}

        def fake_save(cfg):
            captured["cfg"] = cfg

        with (
            mock.patch(
                "multi_memory.cli.load_config",
                return_value={"memory": {"multi": {"backends": "corrupt"}}},
            ),
            mock.patch("multi_memory.cli.save_config", side_effect=fake_save),
        ):
            _cmd_add(args)

        out = capsys.readouterr().out
        assert "Added" in out
        backends = captured["cfg"]["memory"]["multi"]["backends"]
        assert isinstance(backends, dict)
        assert "holographic" in backends

    def test_add_with_non_list_providers(self, capsys):
        """Pre-existing non-list 'providers' value must be coerced."""
        from multi_memory.cli import _cmd_add

        args = argparse.Namespace(backend="holographic", multi_command="add")
        captured = {}

        def fake_save(cfg):
            captured["cfg"] = cfg

        with (
            mock.patch(
                "multi_memory.cli.load_config",
                return_value={
                    "memory": {
                        "multi": {"backends": {}},
                        "providers": "not-a-list",
                    }
                },
            ),
            mock.patch("multi_memory.cli.save_config", side_effect=fake_save),
        ):
            _cmd_add(args)

        out = capsys.readouterr().out
        assert "Added" in out
        providers = captured["cfg"]["memory"]["providers"]
        assert isinstance(providers, list)
        assert "holographic" in providers


# ── _install_dependencies guards ─────────────────────────────────────────


class TestInstallDepsNonDictMeta:
    """_install_dependencies must handle non-dict meta from yaml."""

    def test_non_dict_meta_returns_silently(self, tmp_path, capsys):
        """If yaml.safe_load returns a non-dict (e.g. a bare string),
        _install_dependencies must return without crashing."""
        from multi_memory.cli import _install_dependencies

        plugin_dir = tmp_path / "fake-plugin"
        plugin_dir.mkdir()
        yaml_path = plugin_dir / "plugin.yaml"
        yaml_path.write_text("just a string")

        with mock.patch("multi_memory.cli._find_provider_dir", return_value=plugin_dir):
            _install_dependencies("fake-plugin")

        # No crash, no output — function returned early
        out = capsys.readouterr().out
        assert "Installing" not in out


class TestInstallDepsNonDictExtDeps:
    """_install_dependencies must handle non-dict entries in ext_deps."""

    def test_ext_deps_non_list_returns(self, tmp_path):
        """If ext_deps is a non-list value, function must not crash."""
        from multi_memory.cli import _install_dependencies

        plugin_dir = tmp_path / "fake-plugin"
        plugin_dir.mkdir()
        yaml_path = plugin_dir / "plugin.yaml"
        yaml_path.write_text("pip_dependencies: []\nexternal_dependencies: 'not-a-list'\n")

        with mock.patch("multi_memory.cli._find_provider_dir", return_value=plugin_dir):
            # Must not raise
            _install_dependencies("fake-plugin")

    def test_ext_deps_non_dict_item_skipped(self, tmp_path):
        """If ext_deps contains a non-dict item, it must be skipped."""
        from multi_memory.cli import _install_dependencies

        plugin_dir = tmp_path / "fake-plugin"
        plugin_dir.mkdir()
        yaml_path = plugin_dir / "plugin.yaml"
        yaml_path.write_text(
            "pip_dependencies: []\n"
            "external_dependencies:\n"
            "  - 'just-a-string'\n"
            "  - name: valid\n"
            "    check: 'echo ok'\n"
            "    install: 'echo install'\n"
        )

        with mock.patch("multi_memory.cli._find_provider_dir", return_value=plugin_dir):
            # Must not raise
            _install_dependencies("fake-plugin")


# ── config.py coverage: unexpected exception in load_full_config ─────────


class TestLoadFullConfigEdgeCases:
    """Cover the generic except clause in load_full_config."""

    def test_generic_exception_returns_empty(self):
        """If an unexpected error occurs (not FileNotFoundError, PermissionError,
        IsADirectoryError, or YAMLError), load_full_config must return {}."""
        from multi_memory import config as cfg_mod

        with mock.patch("builtins.open", side_effect=OSError("unexpected")):
            result = cfg_mod.load_full_config()
        assert result == {}


# ── _cmd_status JSON output with non-dict memory_cfg ─────────────────────


class TestCmdStatusJsonNonDictMemory:
    """JSON status output must not crash with non-dict memory_cfg."""

    def test_json_output_with_non_dict_memory(self, capsys):
        import json

        from multi_memory.cli import _cmd_status

        args = argparse.Namespace(json_output=True, multi_command="status")
        with (
            mock.patch("multi_memory.cli.load_config", return_value={"memory": 42}),
            mock.patch("multi_memory.cli._get_available_backends", return_value=[]),
        ):
            _cmd_status(args)

        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["active_backends"] == []
        assert data["config_format"] == "providers"
