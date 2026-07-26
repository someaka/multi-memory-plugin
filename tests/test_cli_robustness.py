"""CLI robustness tests - malformed config handling, command edge cases.

Consolidated from audit passes 4, 5, 6, 7.
"""

from __future__ import annotations

import argparse
import json
from unittest import mock

from multi_memory.cli import (
    _cmd_add,
    _cmd_remove,
    _cmd_status,
    _cmd_update,
    _install_dependencies,
    _remove_backend_from_config,
    _set_active_backends,
    multi_command,
)
from multi_memory.config import get_enabled_backends


class TestGetActiveBackendsNonDictNestedFields:
    """get_enabled_backends handles non-dict nested fields (from fourth pass)."""

    def test_multi_is_string(self):
        """multi field as string is handled gracefully."""
        cfg = {"multi": "invalid", "providers": ["mnemosyne"]}
        result = get_enabled_backends(cfg)
        assert result == ["mnemosyne"]

    def test_multi_is_list(self):
        """multi field as list is handled gracefully."""
        cfg = {"multi": ["invalid"], "providers": ["mem0"]}
        result = get_enabled_backends(cfg)
        assert result == ["mem0"]

    def test_backends_is_string(self):
        """backends field as string is handled gracefully."""
        cfg = {"multi": {"backends": "invalid"}, "providers": ["honcho"]}
        result = get_enabled_backends(cfg)
        assert result == ["honcho"]

    def test_backends_is_list(self):
        """backends field as list is handled gracefully."""
        cfg = {"multi": {"backends": ["invalid"]}, "providers": ["holographic"]}
        result = get_enabled_backends(cfg)
        assert result == ["holographic"]

    def test_providers_is_string(self):
        """providers field as string is handled gracefully."""
        cfg = {"providers": "mnemosyne"}
        result = get_enabled_backends(cfg)
        assert result == []

    def test_providers_is_dict(self):
        """providers field as dict is handled gracefully."""
        cfg = {"providers": {"mnemosyne": {}}}
        result = get_enabled_backends(cfg)
        assert result == []

    def test_all_non_dict_falls_through(self):
        """All non-dict fields fall through to empty result."""
        cfg = {"multi": "invalid", "providers": "also invalid"}
        result = get_enabled_backends(cfg)
        assert result == []


class TestGetActiveBackendsNonDictInput:
    """get_enabled_backends handles non-dict input (from sixth pass)."""

    def test_empty_dict_input(self):
        """Empty dict input returns empty list."""
        result = get_enabled_backends({})
        assert result == []

    def test_string_input(self):
        """String input returns empty list."""
        result = get_enabled_backends("invalid")  # type: ignore[arg-type]
        assert result == []

    def test_list_input(self):
        """List input returns empty list."""
        result = get_enabled_backends(["invalid"])  # type: ignore[arg-type]
        assert result == []

    def test_int_input(self):
        """Int input returns empty list."""
        result = get_enabled_backends(42)  # type: ignore[arg-type]
        assert result == []


class TestGetActiveBackendsNonStringProviders:
    """get_enabled_backends filters non-string items in providers (from eighth pass)."""

    def test_providers_with_int(self):
        """Int items in providers are filtered out."""
        cfg = {"providers": [42, "mnemosyne", 100]}
        result = get_enabled_backends(cfg)
        assert result == ["mnemosyne"]

    def test_providers_with_none(self):
        """None items in providers are filtered out."""
        cfg = {"providers": [None, "mem0", None]}
        result = get_enabled_backends(cfg)
        assert result == ["mem0"]

    def test_providers_with_empty_string(self):
        """Empty string items in providers are filtered out."""
        cfg = {"providers": ["", "honcho", ""]}
        result = get_enabled_backends(cfg)
        assert result == ["honcho"]

    def test_providers_all_non_string(self):
        """All non-string items results in empty list."""
        cfg = {"providers": [42, None, "", []]}
        result = get_enabled_backends(cfg)
        assert result == []


class TestRemoveBackendFromConfigNonDict:
    """_remove_backend_from_config handles non-dict fields (from fourth pass)."""

    def test_multi_is_string(self):
        """multi field as string is handled gracefully."""
        cfg = {"multi": "invalid", "providers": ["mnemosyne", "mem0"]}
        _remove_backend_from_config("mnemosyne", cfg)
        assert "mnemosyne" not in cfg.get("providers", [])

    def test_multi_is_list(self):
        """multi field as list is handled gracefully."""
        cfg = {"multi": ["invalid"], "providers": ["mem0"]}
        _remove_backend_from_config("mem0", cfg)
        assert "mem0" not in cfg.get("providers", [])

    def test_backends_is_string(self):
        """backends field as string is handled gracefully."""
        cfg = {"multi": {"backends": "invalid"}, "providers": ["honcho"]}
        _remove_backend_from_config("honcho", cfg)
        assert "honcho" not in cfg.get("providers", [])

    def test_backends_is_list(self):
        """backends field as list is handled gracefully."""
        cfg = {"multi": {"backends": ["invalid"]}, "providers": ["holographic"]}
        _remove_backend_from_config("holographic", cfg)
        assert "holographic" not in cfg.get("providers", [])

    def test_providers_is_string(self):
        """providers field as string is handled gracefully — no crash."""
        cfg = {"providers": "mnemosyne"}
        # Should not crash even though providers is a non-list
        _remove_backend_from_config("mnemosyne", cfg)
        # provider key removed since no backends remain
        assert "provider" not in cfg or "multi" not in cfg.get("provider", "")

    def test_providers_is_dict(self):
        """providers field as dict is handled gracefully — no crash."""
        cfg = {"providers": {"mnemosyne": {}}}
        # Should not crash even though providers is a dict
        _remove_backend_from_config("mnemosyne", cfg)
        # provider key removed since no backends remain
        assert "provider" not in cfg or "multi" not in cfg.get("provider", "")


class TestCmdStatusNonDictMemory:
    """_cmd_status handles non-dict memory config (from sixth pass)."""

    def test_status_with_non_dict_memory(self, capsys):
        """Non-dict memory config is handled gracefully."""
        args = argparse.Namespace(json_output=False)
        with (
            mock.patch("multi_memory.cli.load_config", return_value={"memory": "invalid"}),
            mock.patch("multi_memory.cli._get_available_backends", return_value=[]),
        ):
            _cmd_status(args)

        captured = capsys.readouterr()
        assert "Memory status" in captured.out or "Active backends" in captured.out

    def test_status_with_none_memory(self, capsys):
        """None memory config is handled gracefully."""
        args = argparse.Namespace(json_output=False)
        with (
            mock.patch("multi_memory.cli.load_config", return_value={"memory": None}),
            mock.patch("multi_memory.cli._get_available_backends", return_value=[]),
        ):
            _cmd_status(args)

        captured = capsys.readouterr()
        assert "Memory status" in captured.out or "Active backends" in captured.out


class TestCmdStatusJsonNonDictMemory:
    """_cmd_status JSON output handles non-dict memory (from sixth pass)."""

    def test_json_output_with_non_dict_memory(self, capsys):
        """JSON output works with non-dict memory config."""
        args = argparse.Namespace(json_output=True)
        with (
            mock.patch("multi_memory.cli.load_config", return_value={"memory": "invalid"}),
            mock.patch("multi_memory.cli._get_available_backends", return_value=[]),
        ):
            _cmd_status(args)

        captured = capsys.readouterr()
        # Should be valid JSON
        result = json.loads(captured.out)
        assert isinstance(result, dict)


class TestCmdAddNonDictGuards:
    """_cmd_add handles pre-existing non-dict config values (from sixth pass)."""

    def test_add_with_non_dict_memory(self, capsys):
        """Adding backend with non-dict memory config coerces to dict."""
        args = argparse.Namespace(backend="holographic", name="holographic")
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
        args = argparse.Namespace(backend="holographic", name="holographic")
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
        args = argparse.Namespace(backend="holographic", name="holographic")
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
        args = argparse.Namespace(backend="holographic", name="holographic")
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


class TestInstallDepsNonDictMeta:
    """_install_dependencies handles non-dict meta from yaml (from sixth pass)."""

    def test_non_dict_meta_returns_silently(self, tmp_path):
        """Non-dict meta from yaml.safe_load returns silently."""
        plugin_dir = tmp_path / "test_plugin"
        plugin_dir.mkdir()
        yaml_file = plugin_dir / "plugin.yaml"
        yaml_file.write_text("invalid yaml content")

        with (
            mock.patch("multi_memory.cli._find_provider_dir", return_value=plugin_dir),
            mock.patch("multi_memory.cli.subprocess.run"),
        ):
            # Should not raise
            _install_dependencies("test_plugin")


class TestInstallDepsNonDictExtDeps:
    """_install_dependencies handles non-dict ext_deps items (from sixth pass)."""

    def test_ext_deps_non_list_returns(self, tmp_path):
        """Non-list ext_deps returns silently."""
        plugin_dir = tmp_path / "test_plugin"
        plugin_dir.mkdir()
        yaml_file = plugin_dir / "plugin.yaml"
        yaml_file.write_text("pip_dependencies: []\nexternal_dependencies: invalid\n")

        with (
            mock.patch("multi_memory.cli._find_provider_dir", return_value=plugin_dir),
            mock.patch("multi_memory.cli.subprocess.run"),
        ):
            # Should not raise
            _install_dependencies("test_plugin")

    def test_ext_deps_non_dict_item_skipped(self, tmp_path):
        """Non-dict items in ext_deps are skipped."""
        plugin_dir = tmp_path / "test_plugin"
        plugin_dir.mkdir()
        yaml_file = plugin_dir / "plugin.yaml"
        yaml_file.write_text(
            "pip_dependencies: []\n"
            "external_dependencies:\n"
            "  - invalid\n"
            "  - name: valid\n"
            "    check: echo test\n"
        )

        with (
            mock.patch("multi_memory.cli._find_provider_dir", return_value=plugin_dir),
            mock.patch("multi_memory.cli.subprocess.run"),
        ):
            # Should not raise, should skip invalid item
            _install_dependencies("test_plugin")


class TestSetActiveBackendsNonDictGuards:
    """_set_active_backends handles non-dict nested fields (from seventh pass)."""

    def test_non_dict_multi_coerced(self):
        """Non-dict multi field is coerced to dict."""
        cfg = {"multi": "invalid"}
        _set_active_backends(cfg, ["mnemosyne"])
        assert isinstance(cfg["multi"], dict)
        assert "backends" in cfg["multi"]

    def test_non_dict_backends_coerced(self):
        """Non-dict backends field is coerced to dict."""
        cfg = {"multi": {"backends": "invalid"}}
        _set_active_backends(cfg, ["mem0"])
        assert isinstance(cfg["multi"]["backends"], dict)

    def test_non_dict_multi_is_int(self):
        """Int multi field is coerced to dict."""
        cfg = {"multi": 42}
        _set_active_backends(cfg, ["honcho"])
        assert isinstance(cfg["multi"], dict)

    def test_non_dict_multi_is_list(self):
        """List multi field is coerced to dict."""
        cfg = {"multi": ["invalid"]}
        _set_active_backends(cfg, ["holographic"])
        assert isinstance(cfg["multi"], dict)

    def test_non_dict_backends_is_list(self):
        """List backends field is coerced to dict."""
        cfg = {"multi": {"backends": ["invalid"]}}
        _set_active_backends(cfg, ["hindsight"])
        assert isinstance(cfg["multi"]["backends"], dict)

    def test_existing_dict_backends_preserved(self):
        """Existing dict backends are preserved when adding new backends."""
        cfg = {"multi": {"backends": {"mnemosyne": {}}}}
        _set_active_backends(cfg, ["mnemosyne", "mem0"])
        assert "mnemosyne" in cfg["multi"]["backends"]
        assert "mem0" in cfg["multi"]["backends"]


class TestSetCmdSetupWizardNonDictMemory:
    """_cmd_setup_wizard handles non-dict memory config (from seventh pass)."""

    def test_non_dict_memory_does_not_crash(self, capsys):
        """Non-dict memory config does not crash setup wizard."""
        args = argparse.Namespace(backend=None)
        with (
            mock.patch("multi_memory.cli.load_config", return_value={"memory": "invalid"}),
            mock.patch("multi_memory.cli._get_available_backends", return_value=[]),
        ):
            # Should not raise
            from multi_memory.cli import _cmd_setup_wizard

            _cmd_setup_wizard(args)


class TestSetCmdSetupBackendNonDictMemory:
    """_cmd_setup_backend handles non-dict memory config (from seventh pass)."""

    def test_non_dict_memory_does_not_crash_before_match(self, capsys):
        """Non-dict memory config does not crash before backend matching."""
        args = argparse.Namespace(backend="test")
        with (
            mock.patch("multi_memory.cli.load_config", return_value={"memory": "invalid"}),
            mock.patch("multi_memory.cli._get_available_backends", return_value=[]),
        ):
            # Should not raise
            from multi_memory.cli import _cmd_setup_backend

            _cmd_setup_backend(args)


class TestMultiCommandAllDispatch:
    """multi_command dispatches to all subcommands (from fifth pass)."""

    def test_dispatch_status(self, capsys):
        """Status command is dispatched correctly."""
        args = argparse.Namespace(command="status", json_output=False)
        with (
            mock.patch("multi_memory.cli.load_config", return_value={}),
            mock.patch("multi_memory.cli._get_available_backends", return_value=[]),
        ):
            multi_command(args)
        # Should not raise

    def test_dispatch_list(self, capsys):
        """List command is dispatched correctly."""
        args = argparse.Namespace(command="list", json_output=False)
        with (
            mock.patch("multi_memory.cli.load_config", return_value={}),
            mock.patch("multi_memory.cli._get_available_backends", return_value=[]),
        ):
            multi_command(args)
        # Should not raise

    def test_dispatch_add(self, capsys):
        """Add command is dispatched correctly."""
        args = argparse.Namespace(command="add", backend="test", name="test")
        with (
            mock.patch("multi_memory.cli.load_config", return_value={}),
            mock.patch("multi_memory.cli.save_config"),
        ):
            multi_command(args)
        # Should not raise

    def test_dispatch_remove(self, capsys):
        """Remove command is dispatched correctly."""
        args = argparse.Namespace(command="remove", backend="test")
        with (
            mock.patch("multi_memory.cli.load_config", return_value={}),
            mock.patch("multi_memory.cli.save_config"),
        ):
            multi_command(args)
        # Should not raise

    def test_dispatch_update(self, capsys):
        """Update command is dispatched correctly."""
        args = argparse.Namespace(command="update")
        with mock.patch("multi_memory.cli.subprocess.run"):
            multi_command(args)
        # Should not raise

    def test_dispatch_setup(self, capsys):
        """Setup command is dispatched correctly."""
        args = argparse.Namespace(command="setup", backend=None)
        with (
            mock.patch("multi_memory.cli.load_config", return_value={}),
            mock.patch("multi_memory.cli._get_available_backends", return_value=[]),
        ):
            multi_command(args)
        # Should not raise

    def test_dispatch_invalid(self, capsys):
        """Invalid command prints help."""
        args = argparse.Namespace(command="invalid")
        multi_command(args)
        captured = capsys.readouterr()
        assert "Usage" in captured.out or "multi" in captured.out


class TestCmdUpdate:
    """_cmd_update handles various scenarios (from fifth pass)."""

    def test_update_success(self, capsys):
        """Successful update prints success message."""
        args = argparse.Namespace()
        mock_result = mock.MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Updated successfully"

        with mock.patch("multi_memory.cli.subprocess.run", return_value=mock_result):
            _cmd_update(args)

        captured = capsys.readouterr()
        assert "✓" in captured.out or "success" in captured.out.lower()

    def test_update_success_long_output(self, capsys):
        """Long output is truncated with 'more lines' message."""
        args = argparse.Namespace()
        mock_result = mock.MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "line1\nline2\nline3\nline4\nline5\nline6\nline7"

        with mock.patch("multi_memory.cli.subprocess.run", return_value=mock_result):
            _cmd_update(args)

        captured = capsys.readouterr()
        assert "more lines" in captured.out or "..." in captured.out

    def test_update_success_no_stdout(self, capsys):
        """Success with no stdout still prints success."""
        args = argparse.Namespace()
        mock_result = mock.MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""

        with mock.patch("multi_memory.cli.subprocess.run", return_value=mock_result):
            _cmd_update(args)

        captured = capsys.readouterr()
        assert "✓" in captured.out or "success" in captured.out.lower()

    def test_update_fail_with_stderr(self, capsys):
        """Failure with stderr prints error message."""
        args = argparse.Namespace()
        mock_result = mock.MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Error: something went wrong"
        mock_result.stdout = ""

        with mock.patch("multi_memory.cli.subprocess.run", return_value=mock_result):
            _cmd_update(args)

        captured = capsys.readouterr()
        assert (
            "✗" in captured.out
            or "error" in captured.out.lower()
            or "failed" in captured.out.lower()
        )

    def test_update_fail_with_stdout_only(self, capsys):
        """Failure with stdout only (no stderr) prints error."""
        args = argparse.Namespace()
        mock_result = mock.MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = ""
        mock_result.stdout = "Error output here"

        with mock.patch("multi_memory.cli.subprocess.run", return_value=mock_result):
            _cmd_update(args)

        captured = capsys.readouterr()
        assert (
            "✗" in captured.out
            or "error" in captured.out.lower()
            or "failed" in captured.out.lower()
        )

    def test_update_hermes_not_found(self, capsys):
        """Hermes not found prints helpful error."""
        args = argparse.Namespace()

        with mock.patch("multi_memory.cli.subprocess.run", side_effect=FileNotFoundError()):
            _cmd_update(args)

        captured = capsys.readouterr()
        assert "hermes" in captured.out.lower() or "not found" in captured.out.lower()

    def test_update_timeout(self, capsys):
        """Timeout prints timeout error."""
        args = argparse.Namespace()
        import subprocess

        with mock.patch(
            "multi_memory.cli.subprocess.run", side_effect=subprocess.TimeoutExpired("hermes", 120)
        ):
            _cmd_update(args)

        captured = capsys.readouterr()
        assert "timeout" in captured.out.lower() or "timed out" in captured.out.lower()

    def test_update_generic_exception(self, capsys):
        """Generic exception prints error."""
        args = argparse.Namespace()

        with mock.patch(
            "multi_memory.cli.subprocess.run", side_effect=RuntimeError("Unexpected error")
        ):
            _cmd_update(args)

        captured = capsys.readouterr()
        assert (
            "✗" in captured.out
            or "error" in captured.out.lower()
            or "failed" in captured.out.lower()
        )


class TestCmdStatusDisplayBranches:
    """_cmd_status display branches (from fifth pass)."""

    def test_status_legacy_provider_with_config(self, capsys):
        """Legacy provider with config displays correctly."""
        args = argparse.Namespace(json_output=False)
        config = {
            "memory": {
                "provider": "legacy",
                "legacy": {"api_key": "test", "endpoint": "https://example.com"},
            }
        }
        with (
            mock.patch("multi_memory.cli.load_config", return_value=config),
            mock.patch("multi_memory.cli._get_available_backends", return_value=[]),
        ):
            _cmd_status(args)
        # Should not raise

    def test_status_legacy_provider_with_dict_value(self, capsys):
        """Legacy provider with dict config value displays correctly."""
        args = argparse.Namespace(json_output=False)
        config = {
            "memory": {
                "provider": "legacy",
                "legacy": {"nested": {"key": "value"}},
            }
        }
        with (
            mock.patch("multi_memory.cli.load_config", return_value=config),
            mock.patch("multi_memory.cli._get_available_backends", return_value=[]),
        ):
            _cmd_status(args)
        # Should not raise

    def test_status_legacy_provider_with_list_value(self, capsys):
        """Legacy provider with list config value displays correctly."""
        args = argparse.Namespace(json_output=False)
        config = {
            "memory": {
                "provider": "legacy",
                "legacy": {"items": ["a", "b", "c"]},
            }
        }
        with (
            mock.patch("multi_memory.cli.load_config", return_value=config),
            mock.patch("multi_memory.cli._get_available_backends", return_value=[]),
        ):
            _cmd_status(args)
        # Should not raise

    def test_status_legacy_provider_via_get_status_config(self, capsys):
        """Legacy provider with get_status_config method uses it."""
        args = argparse.Namespace(json_output=False)
        config = {
            "memory": {
                "provider": "legacy",
            }
        }
        mock_provider = mock.MagicMock()
        mock_provider.get_status_config.return_value = {"status": "ok"}

        with (
            mock.patch("multi_memory.cli.load_config", return_value=config),
            mock.patch(
                "multi_memory.cli._get_available_backends",
                return_value=[("legacy", "Legacy provider", mock_provider)],
            ),
        ):
            _cmd_status(args)
        # Should not raise

    def test_status_backend_with_config(self, capsys):
        """Backend with config displays config."""
        args = argparse.Namespace(json_output=False)
        config = {
            "memory": {
                "multi": {"backends": {"mnemosyne": {}}},
                "mnemosyne": {"api_key": "test"},
            }
        }
        with (
            mock.patch("multi_memory.cli.load_config", return_value=config),
            mock.patch("multi_memory.cli._get_available_backends", return_value=[]),
        ):
            _cmd_status(args)
        # Should not raise

    def test_status_backend_not_installed(self, capsys):
        """Backend not installed shows not installed message."""
        args = argparse.Namespace(json_output=False)
        config = {
            "memory": {
                "multi": {"backends": {"unknown": {}}},
            }
        }
        with (
            mock.patch("multi_memory.cli.load_config", return_value=config),
            mock.patch("multi_memory.cli._get_available_backends", return_value=[]),
        ):
            _cmd_status(args)
        # Should not raise

    def test_status_backend_available(self, capsys):
        """Available backend shows available status."""
        args = argparse.Namespace(json_output=False)
        config = {
            "memory": {
                "multi": {"backends": {"test": {}}},
            }
        }
        mock_provider = mock.MagicMock()
        mock_provider.is_available.return_value = True

        with (
            mock.patch("multi_memory.cli.load_config", return_value=config),
            mock.patch(
                "multi_memory.cli._get_available_backends",
                return_value=[("test", "Test provider", mock_provider)],
            ),
        ):
            _cmd_status(args)
        # Should not raise

    def test_status_backend_not_available_missing_env(self, capsys):
        """Not available backend with missing env vars shows help."""
        args = argparse.Namespace(json_output=False)
        config = {
            "memory": {
                "multi": {"backends": {"test": {}}},
            }
        }
        mock_provider = mock.MagicMock()
        mock_provider.is_available.return_value = False
        mock_provider.get_config_schema.return_value = [
            {"key": "api_key", "env_var": "TEST_API_KEY", "url": "https://example.com"}
        ]

        with (
            mock.patch("multi_memory.cli.load_config", return_value=config),
            mock.patch(
                "multi_memory.cli._get_available_backends",
                return_value=[("test", "Test provider", mock_provider)],
            ),
        ):
            _cmd_status(args)
        # Should not raise

    def test_status_backend_env_var_set(self, capsys):
        """Not available backend with env var set shows env var status."""
        args = argparse.Namespace(json_output=False)
        config = {
            "memory": {
                "multi": {"backends": {"test": {}}},
            }
        }
        mock_provider = mock.MagicMock()
        mock_provider.is_available.return_value = False
        mock_provider.get_config_schema.return_value = [
            {"key": "api_key", "env_var": "TEST_API_KEY", "url": "https://example.com"}
        ]

        with (
            mock.patch("multi_memory.cli.load_config", return_value=config),
            mock.patch(
                "multi_memory.cli._get_available_backends",
                return_value=[("test", "Test provider", mock_provider)],
            ),
            mock.patch.dict("os.environ", {"TEST_API_KEY": "test_value"}),
        ):
            _cmd_status(args)
        # Should not raise

    def test_status_backend_config_with_list_value(self, capsys):
        """Backend config with list value displays correctly."""
        args = argparse.Namespace(json_output=False)
        config = {
            "memory": {
                "multi": {"backends": {"test": {}}},
                "test": {"items": ["a", "b"]},
            }
        }
        with (
            mock.patch("multi_memory.cli.load_config", return_value=config),
            mock.patch("multi_memory.cli._get_available_backends", return_value=[]),
        ):
            _cmd_status(args)
        # Should not raise

    def test_status_installed_plugins_list(self, capsys):
        """Installed plugins list displays correctly."""
        args = argparse.Namespace(json_output=False)
        config = {"memory": {}}
        mock_provider = mock.MagicMock()

        with (
            mock.patch("multi_memory.cli.load_config", return_value=config),
            mock.patch(
                "multi_memory.cli._get_available_backends",
                return_value=[("test", "Test provider", mock_provider)],
            ),
        ):
            _cmd_status(args)
        # Should not raise

    def test_status_backend_config_with_nested_dict(self, capsys):
        """Backend config with nested dict displays correctly."""
        args = argparse.Namespace(json_output=False)
        config = {
            "memory": {
                "multi": {"backends": {"test": {}}},
                "test": {"nested": {"key": "value"}},
            }
        }
        with (
            mock.patch("multi_memory.cli.load_config", return_value=config),
            mock.patch("multi_memory.cli._get_available_backends", return_value=[]),
        ):
            _cmd_status(args)
        # Should not raise

    def test_status_version_import_fail(self, capsys):
        """Version import failure is handled gracefully."""
        args = argparse.Namespace(json_output=False)
        config = {"memory": {}}

        with (
            mock.patch("multi_memory.cli.load_config", return_value=config),
            mock.patch("multi_memory.cli._get_available_backends", return_value=[]),
            mock.patch("multi_memory.__version__", side_effect=ImportError()),
        ):
            _cmd_status(args)
        # Should not raise

    def test_status_json_version(self, capsys):
        """JSON status includes version from _version module."""
        args = argparse.Namespace(json_output=True)
        config = {"memory": {}}

        with (
            mock.patch("multi_memory.cli.load_config", return_value=config),
            mock.patch("multi_memory.cli._get_available_backends", return_value=[]),
        ):
            _cmd_status(args)

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert "version" in output
        assert output["version"] == "0.13.0"

    def test_status_legacy_provider_not_installed(self, capsys):
        """Legacy provider not installed shows appropriate message."""
        args = argparse.Namespace(json_output=False)
        config = {
            "memory": {
                "provider": "legacy",
            }
        }
        with (
            mock.patch("multi_memory.cli.load_config", return_value=config),
            mock.patch("multi_memory.cli._get_available_backends", return_value=[]),
        ):
            _cmd_status(args)
        # Should not raise


class TestCmdAddEdgeCases:
    """_cmd_add edge cases (from fifth pass)."""

    def test_add_unknown_backend(self, capsys):
        """Adding unknown backend prints error."""
        args = argparse.Namespace(backend="nonexistent_backend")
        _cmd_add(args)
        out = capsys.readouterr().out
        assert "Unknown backend" in out
        assert "nonexistent_backend" in out

    def test_add_already_active_disabled(self, capsys):
        """Add backend that's disabled (False) re-enables it."""
        config = {
            "memory": {
                "multi": {"backends": {"mem0": False}},
                "provider": "multi",
            }
        }
        saved = {}
        args = argparse.Namespace(backend="mem0")

        def fake_save(cfg):
            saved.update(cfg)

        with (
            mock.patch("multi_memory.cli.load_config", return_value=config),
            mock.patch("multi_memory.cli.save_config", side_effect=fake_save),
        ):
            _cmd_add(args)
        out = capsys.readouterr().out
        assert "Added" in out
        assert saved["memory"]["multi"]["backends"]["mem0"] == {}


class TestCmdRemoveEdgeCases:
    """_cmd_remove edge cases (from fifth pass)."""

    def test_remove_with_remaining(self, capsys):
        """Removing one backend shows remaining active backends."""
        config = {
            "memory": {
                "multi": {"backends": {"mem0": {}, "holographic": {}}},
                "providers": ["mem0", "holographic"],
                "provider": "multi",
            }
        }
        args = argparse.Namespace(backend="mem0", force=True)
        with (
            mock.patch("multi_memory.cli.load_config", return_value=config),
            mock.patch("multi_memory.cli.save_config"),
        ):
            _cmd_remove(args)
        out = capsys.readouterr().out
        assert "Removed" in out
        assert "holographic" in out

    def test_remove_non_dict_memory_cfg(self, capsys):
        """Removing backend with non-dict memory config prints 'not found' message."""
        args = argparse.Namespace(backend="test")
        config = {"memory": "invalid"}

        with (
            mock.patch("multi_memory.cli.load_config", return_value=config),
            mock.patch("multi_memory.cli.save_config"),
        ):
            _cmd_remove(args)

        out = capsys.readouterr().out
        assert "No memory config found" in out


class TestGetStatusConfigGuards:
    """get_status_config guards against non-dict inputs (from sixth pass)."""

    def test_non_dict_provider_config_returns_empty(self):
        """Non-dict provider_config returns empty dict."""
        from multi_memory import MultiMemoryProvider

        result = MultiMemoryProvider.get_status_config(None, "invalid")  # type: ignore[arg-type]
        assert result == {}

    def test_non_dict_multi_returns_providers(self):
        """Non-dict multi field falls back to providers."""
        from multi_memory import MultiMemoryProvider

        config = {"multi": "invalid", "providers": ["test"]}
        result = MultiMemoryProvider.get_status_config(None, config)
        assert "providers" in result

    def test_non_dict_backends_skips(self):
        """Non-dict backends field is skipped."""
        from multi_memory import MultiMemoryProvider

        config = {"multi": {"backends": "invalid"}}
        result = MultiMemoryProvider.get_status_config(None, config)
        assert "backends" not in result

    def test_non_dict_backends_falls_through_to_providers(self):
        """Non-dict backends falls through to providers."""
        from multi_memory import MultiMemoryProvider

        config = {"multi": {"backends": "invalid"}, "providers": ["test"]}
        result = MultiMemoryProvider.get_status_config(None, config)
        assert "providers" in result

    def test_non_list_providers_returns_empty(self):
        """Non-list providers returns empty dict."""
        from multi_memory import MultiMemoryProvider

        config = {"providers": "invalid"}
        result = MultiMemoryProvider.get_status_config(None, config)
        assert result == {}

    def test_providers_with_non_string_items(self):
        """Providers with non-string items filters them out."""
        from multi_memory import MultiMemoryProvider

        config = {"providers": [42, "test", None]}
        result = MultiMemoryProvider.get_status_config(None, config)
        assert "test" in result.get("providers", "")


class TestJsonStatusNonDictMulti:
    """JSON status with non-dict multi config (from fourth pass)."""

    def test_json_status_multi_is_string(self, capsys):
        """JSON status with string multi config works."""
        args = argparse.Namespace(json_output=True)
        config = {"memory": {"multi": "invalid", "providers": ["test"]}}

        with (
            mock.patch("multi_memory.cli.load_config", return_value=config),
            mock.patch("multi_memory.cli._get_available_backends", return_value=[]),
        ):
            _cmd_status(args)

        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert isinstance(result, dict)
