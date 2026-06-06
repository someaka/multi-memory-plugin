"""Tests for the multi-memory CLI commands."""
# ruff: noqa: PLR2004  # magic numbers in tests are normal

from __future__ import annotations

import argparse
import json
from unittest import mock

import pytest

from multi_memory.cli import (
    _cmd_add,
    _cmd_list,
    _cmd_remove,
    _cmd_status,
    multi_command,
    register_cli,
)


@pytest.fixture()
def parser():
    """Build a minimal argparse setup matching Hermes CLI."""
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="command")
    multi_sub = sub.add_parser("multi")
    register_cli(multi_sub)
    return p


# ── register_cli ──────────────────────────────────────────────────────────


class TestRegisterCLI:
    def test_registers_subcommands(self, parser):
        """register_cli adds status/list/add/remove/setup subcommands."""
        args = parser.parse_args(["multi", "status"])
        assert args.multi_command == "status"

        args = parser.parse_args(["multi", "list"])
        assert args.multi_command == "list"

        args = parser.parse_args(["multi", "add", "mem0"])
        assert args.multi_command == "add"
        assert args.backend == "mem0"

        args = parser.parse_args(["multi", "remove", "mem0"])
        assert args.multi_command == "remove"
        assert args.backend == "mem0"

        args = parser.parse_args(["multi", "setup"])
        assert args.multi_command == "setup"
        assert args.backend is None

        args = parser.parse_args(["multi", "setup", "mem0"])
        assert args.multi_command == "setup"
        assert args.backend == "mem0"

    def test_json_flag(self, parser):
        """--json flag is accepted on status and list."""
        args = parser.parse_args(["multi", "status", "--json"])
        assert args.json_output is True

        args = parser.parse_args(["multi", "list", "--json"])
        assert args.json_output is True


# ── multi_command dispatch ────────────────────────────────────────────────


class TestMultiCommandDispatch:
    def test_no_subcommand_prints_help(self, capsys):
        args = argparse.Namespace(multi_command=None)
        multi_command(args)
        out = capsys.readouterr().out
        assert "Usage: hermes multi" in out

    def test_unknown_subcommand(self, capsys):
        args = argparse.Namespace(multi_command="bogus")
        multi_command(args)
        out = capsys.readouterr().out
        assert "Usage: hermes multi" in out


# ── status ────────────────────────────────────────────────────────────────


class TestCmdStatus:
    def test_status_with_backends(self, capsys):
        """status shows active backends from config."""
        config = {
            "memory": {
                "provider": "multi",
                "multi": {"backends": {"mnemosyne": {}, "holographic": {}}},
            }
        }
        args = argparse.Namespace(json_output=False)
        with (
            mock.patch("multi_memory.cli.load_config", return_value=config),
            mock.patch("multi_memory.cli.get_hermes_home", return_value="/tmp/.hermes"),
        ):
            _cmd_status(args)
        out = capsys.readouterr().out
        assert "mnemosyne" in out
        assert "holographic" in out
        assert "installed" in out

    def test_status_providers_list_format(self, capsys):
        """status handles providers list format."""
        config = {"memory": {"providers": ["mem0", "honcho"]}}
        args = argparse.Namespace(json_output=False)
        with (
            mock.patch("multi_memory.cli.load_config", return_value=config),
            mock.patch("multi_memory.cli.get_hermes_home", return_value="/tmp/.hermes"),
        ):
            _cmd_status(args)
        out = capsys.readouterr().out
        assert "mem0" in out
        assert "honcho" in out
        assert "Providers:" in out

    def test_status_json(self, capsys):
        """status --json outputs valid JSON."""
        config = {"memory": {"provider": "multi", "multi": {"backends": {"mnemosyne": {}}}}}
        args = argparse.Namespace(json_output=True)
        with mock.patch("multi_memory.cli.load_config", return_value=config):
            _cmd_status(args)
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["provider"] == "multi"
        assert "mnemosyne" in data["active_backends"]

    def test_status_empty(self, capsys):
        """status with no backends shows built-in only."""
        config = {"memory": {}}
        args = argparse.Namespace(json_output=False)
        with (
            mock.patch("multi_memory.cli.load_config", return_value=config),
            mock.patch("multi_memory.cli.get_hermes_home", return_value="/tmp/.hermes"),
        ):
            _cmd_status(args)
        out = capsys.readouterr().out
        assert "built-in only" in out


# ── list ──────────────────────────────────────────────────────────────────


class TestCmdList:
    def test_list_shows_all_backends(self, capsys):
        """list shows all 9 known backends."""
        config = {"memory": {}}
        args = argparse.Namespace(json_output=False)
        with mock.patch("multi_memory.cli.load_config", return_value=config):
            _cmd_list(args)
        out = capsys.readouterr().out
        for name in [
            "mnemosyne",
            "holographic",
            "mem0",
            "honcho",
            "openviking",
            "hindsight",
            "retaindb",
            "byterover",
            "supermemory",
        ]:
            assert name in out

    def test_list_marks_active(self, capsys):
        """list marks active backends with →."""
        config = {"memory": {"multi": {"backends": {"mnemosyne": {}}}}}
        args = argparse.Namespace(json_output=False)
        with mock.patch("multi_memory.cli.load_config", return_value=config):
            _cmd_list(args)
        out = capsys.readouterr().out
        assert "→" in out

    def test_list_json(self, capsys):
        """list --json outputs valid JSON array."""
        config = {"memory": {}}
        args = argparse.Namespace(json_output=True)
        with mock.patch("multi_memory.cli.load_config", return_value=config):
            _cmd_list(args)
        out = capsys.readouterr().out
        data = json.loads(out)
        assert isinstance(data, list)
        assert len(data) == 9
        names = {r["name"] for r in data}
        assert "mnemosyne" in names
        assert "holographic" in names


# ── add ───────────────────────────────────────────────────────────────────


class TestCmdAdd:
    def test_add_new_backend(self, capsys):
        """add writes backend to both backends dict and providers list."""
        config = {"memory": {}}
        saved = {}
        args = argparse.Namespace(backend="mem0")
        with (
            mock.patch("multi_memory.cli.load_config", return_value=config),
            mock.patch("multi_memory.cli.save_config", side_effect=saved.update),
        ):
            _cmd_add(args)
        assert "memory" in saved

    def test_add_already_active(self, capsys):
        """add on already-active backend prints message."""
        config = {"memory": {"multi": {"backends": {"mem0": {}}}}}
        args = argparse.Namespace(backend="mem0")
        with mock.patch("multi_memory.cli.load_config", return_value=config):
            _cmd_add(args)
        out = capsys.readouterr().out
        assert "already active" in out

    def test_add_empty_name(self, capsys):
        """add with empty name prints usage."""
        args = argparse.Namespace(backend="")
        _cmd_add(args)
        out = capsys.readouterr().out
        assert "Usage:" in out

    def test_add_sets_provider_to_multi(self, capsys):
        """add always sets memory.provider to 'multi'."""
        config = {"memory": {}}
        saved = {}
        args = argparse.Namespace(backend="holographic")
        with (
            mock.patch("multi_memory.cli.load_config", return_value=config),
            mock.patch("multi_memory.cli.save_config", side_effect=saved.update),
        ):
            _cmd_add(args)
        assert saved["memory"]["provider"] == "multi"

    def test_add_overrides_wrong_provider(self, capsys):
        """add corrects provider to 'multi' even if previously wrong."""
        config = {"memory": {"provider": "mnemosyne"}}
        saved = {}
        args = argparse.Namespace(backend="holographic")
        with (
            mock.patch("multi_memory.cli.load_config", return_value=config),
            mock.patch("multi_memory.cli.save_config", side_effect=saved.update),
        ):
            _cmd_add(args)
        assert saved["memory"]["provider"] == "multi"

    def test_add_updates_backends_dict(self, capsys):
        """add updates multi.backends dict."""
        config = {"memory": {}}
        saved = {}
        args = argparse.Namespace(backend="holographic")
        with (
            mock.patch("multi_memory.cli.load_config", return_value=config),
            mock.patch("multi_memory.cli.save_config", side_effect=saved.update),
        ):
            _cmd_add(args)
        assert "holographic" in saved["memory"]["multi"]["backends"]


# ── remove ────────────────────────────────────────────────────────────────


class TestCmdRemove:
    def test_remove_existing(self, capsys):
        """remove deletes backend from config."""
        config = {"memory": {"multi": {"backends": {"mem0": {}}}, "providers": ["mem0"]}}
        saved = {}
        args = argparse.Namespace(backend="mem0")
        with (
            mock.patch("multi_memory.cli.load_config", return_value=config),
            mock.patch("multi_memory.cli.save_config", side_effect=saved.update),
        ):
            _cmd_remove(args)
        out = capsys.readouterr().out
        assert "Removed" in out

    def test_remove_not_found(self, capsys):
        """remove on non-existent backend prints message."""
        config = {"memory": {"multi": {"backends": {"mnemosyne": {}}}}}
        args = argparse.Namespace(backend="mem0")
        with mock.patch("multi_memory.cli.load_config", return_value=config):
            _cmd_remove(args)
        out = capsys.readouterr().out
        assert "not in the active config" in out

    def test_remove_empty_name(self, capsys):
        """remove with empty name prints usage."""
        args = argparse.Namespace(backend="")
        _cmd_remove(args)
        out = capsys.readouterr().out
        assert "Usage:" in out

    def test_remove_last_backend(self, capsys):
        """remove last backend keeps provider=multi (empty multiplexer is valid)."""
        config = {
            "memory": {
                "multi": {"backends": {"mem0": {}}},
                "providers": ["mem0"],
                "provider": "multi",
            }
        }
        saved = {}
        args = argparse.Namespace(backend="mem0")
        call_count = [0]

        def capture_save(cfg):
            call_count[0] += 1
            saved.update(cfg)

        with (
            mock.patch("multi_memory.cli.load_config", return_value=config),
            mock.patch("multi_memory.cli.save_config", side_effect=capture_save),
        ):
            _cmd_remove(args)
        out = capsys.readouterr().out
        assert "Removed" in out
        assert "built-in only" in out


class TestCmdStatusEdgeCases:
    """Coverage for status display edge cases."""

    def test_status_json(self, capsys):
        config = {"memory": {"multi": {"backends": {"mnemosyne": {}}}}}
        args = argparse.Namespace(json_output=True)
        with mock.patch("multi_memory.cli.load_config", return_value=config):
            _cmd_status(args)
        out = capsys.readouterr().out
        import json

        data = json.loads(out)
        assert data["active_backends"] == ["mnemosyne"]

    def test_status_backend_installed(self, capsys):
        config = {"memory": {"multi": {"backends": {"holographic": {}}}}}
        args = argparse.Namespace(json_output=False)
        with mock.patch("multi_memory.cli.load_config", return_value=config):
            _cmd_status(args)
        out = capsys.readouterr().out
        assert "holographic" in out

    def test_status_no_memory_config(self, capsys):
        args = argparse.Namespace(json_output=False)
        with mock.patch("multi_memory.cli.load_config", return_value={}):
            _cmd_status(args)
        out = capsys.readouterr().out
        assert "built-in only" in out

    def test_remove_empty_memory_config(self, capsys):
        args = argparse.Namespace(backend="mnemosyne")
        with mock.patch("multi_memory.cli.load_config", return_value={}):
            _cmd_remove(args)
        out = capsys.readouterr().out
        assert "No memory config found" in out

    def test_status_discovery_exception_silent(self, capsys):
        """status handles discovery exception gracefully."""
        config = {"memory": {"multi": {"backends": {"mnemosyne": {}}}}}
        args = argparse.Namespace(json_output=False)
        with (
            mock.patch("multi_memory.cli.load_config", return_value=config),
            mock.patch(
                "multi_memory.discovery.discover_backends",
                side_effect=RuntimeError("boom"),
            ),
        ):
            _cmd_status(args)
        out = capsys.readouterr().out
        assert "Memory status" in out

    def test_status_reports_only_active_backend(self, capsys):
        config = {"memory": {"multi": {"backends": {"holographic": {}}}}}
        args = argparse.Namespace(json_output=False)
        with mock.patch("multi_memory.cli.load_config", return_value=config):
            _cmd_status(args)
        out = capsys.readouterr().out
        assert "holographic" in out
        # Should show holographic as active, not mnemosyne
        assert " ← active" in out
        active_lines = [line for line in out.split("\n") if " ← active" in line]
        assert any("holographic" in line for line in active_lines)


# ── Config helpers ──────────────────────────────────────────────────────


class TestConfigHelpers:
    def test_set_active_backends_writes_both_formats(self):
        """_set_active_backends writes providers list and multi.backends dict."""
        from multi_memory.cli import _set_active_backends

        memory_cfg: dict = {}
        _set_active_backends(memory_cfg, ["mnemosyne", "holographic"])
        assert memory_cfg["provider"] == "mnemosyne"
        assert memory_cfg["providers"] == ["mnemosyne", "holographic"]
        assert "mnemosyne" in memory_cfg["multi"]["backends"]
        assert "holographic" in memory_cfg["multi"]["backends"]

    def test_set_active_backends_empty_clears(self):
        """_set_active_backends with empty list clears all."""
        from multi_memory.cli import _set_active_backends

        memory_cfg = {
            "provider": "mnemosyne",
            "providers": ["mnemosyne"],
            "multi": {"backends": {"mnemosyne": {}}},
        }
        _set_active_backends(memory_cfg, [])
        assert memory_cfg["provider"] == ""
        assert memory_cfg["providers"] == []

    def test_remove_backend_from_config_both_formats(self):
        """_remove_backend_from_config removes from both formats."""
        from multi_memory.cli import _remove_backend_from_config

        memory_cfg = {
            "provider": "honcho",
            "providers": ["honcho", "mem0"],
            "multi": {"backends": {"honcho": {}, "mem0": {}}},
        }
        _remove_backend_from_config("mem0", memory_cfg)
        assert "mem0" not in memory_cfg["providers"]
        assert "mem0" not in memory_cfg["multi"]["backends"]
        assert "honcho" in memory_cfg["providers"]
        assert memory_cfg["provider"] == "honcho"

    def test_remove_backend_from_config_last_updates_provider(self):
        """_remove_backend_from_config resets provider when last is removed."""
        from multi_memory.cli import _remove_backend_from_config

        memory_cfg = {
            "provider": "honcho",
            "providers": ["honcho"],
            "multi": {"backends": {"honcho": {}}},
        }
        _remove_backend_from_config("honcho", memory_cfg)
        assert memory_cfg["provider"] == ""

    def test_get_active_backends_multi_format(self):
        """_get_active_backends reads multi.backends dict."""
        from multi_memory.cli import _get_active_backends

        active = _get_active_backends({"multi": {"backends": {"mnemosyne": {}, "holographic": {}}}})
        assert active == ["mnemosyne", "holographic"]

    def test_get_active_backends_providers_format(self):
        """_get_active_backends reads providers list."""
        from multi_memory.cli import _get_active_backends

        active = _get_active_backends({"providers": ["mem0", "honcho"]})
        assert active == ["mem0", "honcho"]

    def test_get_active_backends_respects_disabled(self):
        """_get_active_backends skips disabled backends."""
        from multi_memory.cli import _get_active_backends

        active = _get_active_backends({"multi": {"backends": {"mnemosyne": True, "mem0": False}}})
        assert active == ["mnemosyne"]


# ── Prompt helper ───────────────────────────────────────────────────────


class TestPrompt:
    def test_prompt_returns_input(self, monkeypatch):
        """_prompt reads stdin."""
        from multi_memory.cli import _prompt

        monkeypatch.setattr("sys.stdin", __import__("io").StringIO("hello\n"))
        result = _prompt("Name")
        assert result == "hello"

    def test_prompt_returns_default_on_empty(self, monkeypatch):
        """_prompt returns default when input is blank."""
        from multi_memory.cli import _prompt

        monkeypatch.setattr("sys.stdin", __import__("io").StringIO("\n"))
        result = _prompt("Name", default="world")
        assert result == "world"

    def test_prompt_secret_uses_masked(self, monkeypatch):
        """_prompt with secret=True uses masked prompt."""
        from multi_memory.cli import _prompt

        monkeypatch.setattr("multi_memory.cli.masked_secret_prompt", lambda p: "secret123")
        result = _prompt("Key", secret=True)
        assert result == "secret123"


# ── setup command ───────────────────────────────────────────────────────


class TestCmdSetup:
    def test_setup_no_backends(self, capsys):
        """setup with no backends available prints message."""
        args = argparse.Namespace(multi_command="setup", backend=None)
        with mock.patch("multi_memory.cli._get_available_backends", return_value=[]):
            multi_command(args)
        out = capsys.readouterr().out
        assert "No memory backend plugins detected" in out

    def test_setup_backend_not_found(self, capsys):
        """setup <name> with unknown backend prints error."""
        args = argparse.Namespace(multi_command="setup", backend="nonexistent")
        with (
            mock.patch(
                "multi_memory.cli._get_available_backends",
                return_value=[("mnemosyne", "local", None)],
            ),
            mock.patch("multi_memory.cli.load_config", return_value={}),
        ):
            multi_command(args)
        out = capsys.readouterr().out
        assert "not found" in out


# ── dispatch ────────────────────────────────────────────────────────────


class TestDispatchSetup:
    def test_dispatch_setup_calls_wizard(self):
        """multi_command with setup (no backend) calls wizard."""
        args = argparse.Namespace(multi_command="setup", backend=None)
        with mock.patch("multi_memory.cli._cmd_setup_wizard") as m:
            multi_command(args)
        m.assert_called_once()

    def test_dispatch_setup_with_backend(self):
        """multi_command with setup <name> calls backend setup."""
        args = argparse.Namespace(multi_command="setup", backend="mem0")
        with mock.patch("multi_memory.cli._cmd_setup_backend") as m:
            multi_command(args)
        m.assert_called_once_with("mem0")


# ── env var writer ──────────────────────────────────────────────────────


class TestEnvVars:
    def test_write_env_vars_creates_file(self, tmp_path):
        """_write_env_vars creates .env with proper content."""
        from multi_memory.cli import _write_env_vars

        env_path = tmp_path / ".env"
        _write_env_vars(env_path, {"MEM0_API_KEY": "test-key"})
        content = env_path.read_text()
        assert "MEM0_API_KEY=test-key" in content

    def test_write_env_vars_updates_existing(self, tmp_path):
        """_write_env_vars updates existing keys, preserves others."""
        from multi_memory.cli import _write_env_vars

        env_path = tmp_path / ".env"
        env_path.write_text("OLD_KEY=old\nMEM0_API_KEY=new\n")
        _write_env_vars(env_path, {"MEM0_API_KEY": "updated"})
        content = env_path.read_text()
        assert "MEM0_API_KEY=updated" in content
        assert "OLD_KEY=old" in content

    def test_write_env_vars_restricts_permissions(self, tmp_path):
        """_write_env_vars sets 0600 on .env file."""
        from multi_memory.cli import _write_env_vars

        env_path = tmp_path / ".env"
        _write_env_vars(env_path, {"KEY": "val"})
        mode = env_path.stat().st_mode & 0o777
        assert mode == 0o600


# ── find provider dir ───────────────────────────────────────────────────


class TestFindProviderDir:
    def test_find_provider_dir_returns_none_when_discovery_unavailable(self):
        """_find_provider_dir returns None when plugin system unavailable."""
        from multi_memory.cli import _find_provider_dir

        result = _find_provider_dir("mnemosyne")
        assert result is None
