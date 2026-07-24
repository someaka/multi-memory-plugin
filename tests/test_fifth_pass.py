"""Tests for third-pass coverage gaps: _cmd_update, _cmd_status branches,
multi_command dispatch, _cmd_add/remove display paths.

These exercise the previously-uncovered CLI display and dispatch code.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from unittest import mock

import pytest

from multi_memory.cli import (
    _cmd_add,
    _cmd_remove,
    _cmd_status,
    _cmd_update,
    multi_command,
)

_STUB_BACKENDS = [
    ("mnemosyne", "local", None),
    ("mem0", "API key / local", None),
    ("holographic", "local", None),
    ("honcho", "API key / local", None),
    ("openviking", "API key / local", None),
    ("hindsight", "API key / local", None),
    ("retaindb", "API key / local", None),
    ("byterover", "requires API key", None),
    ("supermemory", "requires API key", None),
]


@pytest.fixture(autouse=True)
def _mock_discovery(monkeypatch):
    """Prevent real plugin discovery."""
    monkeypatch.setattr(
        "multi_memory.cli._get_available_backends",
        lambda: _STUB_BACKENDS,
    )


# ── multi_command dispatch coverage ──────────────────────────────────────


class TestMultiCommandAllDispatch:
    """Cover all dispatch branches in multi_command."""

    def test_dispatch_status(self):
        args = argparse.Namespace(multi_command="status")
        with mock.patch("multi_memory.cli._cmd_status") as m:
            multi_command(args)
        m.assert_called_once()

    def test_dispatch_list(self):
        args = argparse.Namespace(multi_command="list")
        with mock.patch("multi_memory.cli._cmd_list") as m:
            multi_command(args)
        m.assert_called_once()

    def test_dispatch_add(self):
        args = argparse.Namespace(multi_command="add", backend="mem0")
        with mock.patch("multi_memory.cli._cmd_add") as m:
            multi_command(args)
        m.assert_called_once()

    def test_dispatch_remove(self):
        args = argparse.Namespace(multi_command="remove", backend="mem0")
        with mock.patch("multi_memory.cli._cmd_remove") as m:
            multi_command(args)
        m.assert_called_once()

    def test_dispatch_update(self):
        args = argparse.Namespace(multi_command="update")
        with mock.patch("multi_memory.cli._cmd_update") as m:
            multi_command(args)
        m.assert_called_once()


# ── _cmd_update ──────────────────────────────────────────────────────────


class TestCmdUpdate:
    """_cmd_update exercises all subprocess.run paths."""

    def test_update_success(self, capsys):
        result = mock.MagicMock()
        result.returncode = 0
        result.stdout = "Updated successfully\nDone\n"
        with mock.patch("multi_memory.cli.subprocess.run", return_value=result):
            _cmd_update(argparse.Namespace())
        out = capsys.readouterr().out
        assert "✓ Plugin updated successfully" in out

    def test_update_success_long_output(self, capsys):
        """More than 5 lines of stdout triggers the 'more lines' summary."""
        result = mock.MagicMock()
        result.returncode = 0
        result.stdout = "\n".join(f"line {i}" for i in range(10))
        with mock.patch("multi_memory.cli.subprocess.run", return_value=result):
            _cmd_update(argparse.Namespace())
        out = capsys.readouterr().out
        assert "more lines)" in out

    def test_update_success_no_stdout(self, capsys):
        result = mock.MagicMock()
        result.returncode = 0
        result.stdout = ""
        with mock.patch("multi_memory.cli.subprocess.run", return_value=result):
            _cmd_update(argparse.Namespace())
        out = capsys.readouterr().out
        assert "✓" in out

    def test_update_fail_with_stderr(self, capsys):
        result = mock.MagicMock()
        result.returncode = 1
        result.stderr = "Network error"
        result.stdout = ""
        with mock.patch("multi_memory.cli.subprocess.run", return_value=result):
            _cmd_update(argparse.Namespace())
        out = capsys.readouterr().out
        assert "✗" in out
        assert "Network error" in out

    def test_update_fail_with_stdout_only(self, capsys):
        result = mock.MagicMock()
        result.returncode = 1
        result.stderr = ""
        result.stdout = "Some error in stdout"
        with mock.patch("multi_memory.cli.subprocess.run", return_value=result):
            _cmd_update(argparse.Namespace())
        out = capsys.readouterr().out
        assert "✗" in out
        assert "Some error" in out

    def test_update_hermes_not_found(self, capsys):
        with mock.patch(
            "multi_memory.cli.subprocess.run",
            side_effect=FileNotFoundError("no hermes"),
        ):
            _cmd_update(argparse.Namespace())
        out = capsys.readouterr().out
        assert "'hermes' command not found" in out

    def test_update_timeout(self, capsys):
        with mock.patch(
            "multi_memory.cli.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="hermes", timeout=120),
        ):
            _cmd_update(argparse.Namespace())
        out = capsys.readouterr().out
        assert "timed out" in out

    def test_update_generic_exception(self, capsys):
        with mock.patch(
            "multi_memory.cli.subprocess.run",
            side_effect=RuntimeError("unexpected"),
        ):
            _cmd_update(argparse.Namespace())
        out = capsys.readouterr().out
        assert "✗" in out
        assert "unexpected" in out


# ── _cmd_status display branches ─────────────────────────────────────────


class TestCmdStatusDisplayBranches:
    """Cover legacy provider display, backend config, env var status."""

    def test_status_legacy_provider_with_config(self, capsys):
        """Legacy non-multi provider config is displayed."""
        config = {
            "memory": {
                "provider": "mem0",
                "mem0": {"api_key": "secret", "endpoint": "https://api.mem0.ai"},
            }
        }
        args = argparse.Namespace(json_output=False)
        with mock.patch("multi_memory.cli.load_config", return_value=config):
            _cmd_status(args)
        out = capsys.readouterr().out
        assert "mem0" in out
        assert "api_key" in out

    def test_status_legacy_provider_with_dict_value(self, capsys):
        """Legacy provider config with nested dict values."""
        config = {
            "memory": {
                "provider": "mem0",
                "mem0": {"options": {"mode": "fast", "cache": True}},
            }
        }
        args = argparse.Namespace(json_output=False)
        with mock.patch("multi_memory.cli.load_config", return_value=config):
            _cmd_status(args)
        out = capsys.readouterr().out
        assert "mode(fast)" in out or "mode" in out

    def test_status_legacy_provider_with_list_value(self, capsys):
        """Legacy provider config with list values."""
        config = {
            "memory": {
                "provider": "mem0",
                "mem0": {"regions": ["us", "eu"]},
            }
        }
        args = argparse.Namespace(json_output=False)
        with mock.patch("multi_memory.cli.load_config", return_value=config):
            _cmd_status(args)
        out = capsys.readouterr().out
        assert "us" in out
        assert "eu" in out

    def test_status_legacy_provider_via_get_status_config(self, capsys):
        """Legacy provider with get_status_config method uses it for display."""
        mock_provider = mock.MagicMock()
        mock_provider.get_status_config.return_value = {"mode": "cloud", "region": "us-east"}
        config = {
            "memory": {
                "provider": "mem0",
                "mem0": {"api_key": "x"},
            }
        }
        args = argparse.Namespace(json_output=False)
        with (
            mock.patch("multi_memory.cli.load_config", return_value=config),
            mock.patch(
                "multi_memory.cli._get_available_backends",
                return_value=[("mem0", "API key", mock_provider)],
            ),
        ):
            _cmd_status(args)
        out = capsys.readouterr().out
        assert "cloud" in out
        assert "us-east" in out

    def test_status_backend_with_config(self, capsys):
        """Active backend with config shows config details."""
        config = {
            "memory": {
                "provider": "multi",
                "multi": {"backends": {"mem0": {}}},
                "mem0": {"api_key": "key123", "endpoint": "https://api.mem0.ai"},
            }
        }
        args = argparse.Namespace(json_output=False)
        with mock.patch("multi_memory.cli.load_config", return_value=config):
            _cmd_status(args)
        out = capsys.readouterr().out
        assert "api_key" in out
        assert "key123" in out

    def test_status_backend_not_installed(self, capsys):
        """Active backend not in installed plugins shows NOT installed."""
        config = {
            "memory": {
                "provider": "multi",
                "multi": {"backends": {"mem0": {}}},
            }
        }
        args = argparse.Namespace(json_output=False)
        with (
            mock.patch("multi_memory.cli.load_config", return_value=config),
            mock.patch(
                "multi_memory.cli._get_available_backends",
                return_value=[],  # no backends installed
            ),
        ):
            _cmd_status(args)
        out = capsys.readouterr().out
        assert "NOT installed" in out

    def test_status_backend_available(self, capsys):
        """Backend that is_available() shows available ✓."""
        mock_provider = mock.MagicMock()
        mock_provider.is_available.return_value = True
        config = {
            "memory": {
                "provider": "multi",
                "multi": {"backends": {"mem0": {}}},
            }
        }
        args = argparse.Namespace(json_output=False)
        with (
            mock.patch("multi_memory.cli.load_config", return_value=config),
            mock.patch(
                "multi_memory.cli._get_available_backends",
                return_value=[("mem0", "API key", mock_provider)],
            ),
        ):
            _cmd_status(args)
        out = capsys.readouterr().out
        assert "available ✓" in out

    def test_status_backend_not_available_missing_env(self, capsys):
        """Backend not available with env_var schema shows missing vars."""
        mock_provider = mock.MagicMock()
        mock_provider.is_available.return_value = False
        mock_provider.get_config_schema.return_value = [
            {"key": "api_key", "env_var": "MEM0_API_KEY", "url": "https://mem0.ai/api"},
        ]
        config = {
            "memory": {
                "provider": "multi",
                "multi": {"backends": {"mem0": {}}},
            }
        }
        args = argparse.Namespace(json_output=False)
        with (
            mock.patch("multi_memory.cli.load_config", return_value=config),
            mock.patch(
                "multi_memory.cli._get_available_backends",
                return_value=[("mem0", "API key", mock_provider)],
            ),
            mock.patch.dict("os.environ", {}, clear=False),
        ):
            _cmd_status(args)
        out = capsys.readouterr().out
        assert "not available" in out
        assert "MEM0_API_KEY" in out

    def test_status_backend_env_var_set(self, capsys):
        """Backend with env var set shows ✓."""
        mock_provider = mock.MagicMock()
        mock_provider.is_available.return_value = False
        mock_provider.get_config_schema.return_value = [
            {"key": "api_key", "env_var": "MEM0_API_KEY", "url": "https://mem0.ai/api"},
        ]
        config = {
            "memory": {
                "provider": "multi",
                "multi": {"backends": {"mem0": {}}},
            }
        }
        args = argparse.Namespace(json_output=False)
        with (
            mock.patch("multi_memory.cli.load_config", return_value=config),
            mock.patch(
                "multi_memory.cli._get_available_backends",
                return_value=[("mem0", "API key", mock_provider)],
            ),
            mock.patch.dict("os.environ", {"MEM0_API_KEY": "test-key"}),
        ):
            _cmd_status(args)
        out = capsys.readouterr().out
        assert "✓ MEM0_API_KEY" in out

    def test_status_backend_config_with_list_value(self, capsys):
        """Active backend config with list values."""
        config = {
            "memory": {
                "provider": "multi",
                "multi": {"backends": {"mem0": {}}},
                "mem0": {"regions": ["us", "eu"]},
            }
        }
        args = argparse.Namespace(json_output=False)
        with mock.patch("multi_memory.cli.load_config", return_value=config):
            _cmd_status(args)
        out = capsys.readouterr().out
        assert "us" in out

    def test_status_installed_plugins_list(self, capsys):
        """Status shows installed plugins list at the bottom."""
        config = {"memory": {}}
        args = argparse.Namespace(json_output=False)
        with mock.patch("multi_memory.cli.load_config", return_value=config):
            _cmd_status(args)
        out = capsys.readouterr().out
        assert "Installed plugins:" in out

    def test_status_backend_config_with_nested_dict(self, capsys):
        """Backend config with nested dict values shows formatted."""
        config = {
            "memory": {
                "provider": "multi",
                "multi": {"backends": {"mem0": {}}},
                "mem0": {"options": {"mode": "fast", "cache": True}},
            }
        }
        args = argparse.Namespace(json_output=False)
        with mock.patch("multi_memory.cli.load_config", return_value=config):
            _cmd_status(args)
        out = capsys.readouterr().out
        assert "options" in out

    def test_status_version_import_fail(self, capsys):
        """Status handles ImportError when multi_memory can't be imported."""
        config = {"memory": {}}
        args = argparse.Namespace(json_output=False)
        with (
            mock.patch("multi_memory.cli.load_config", return_value=config),
            mock.patch(
                "builtins.__import__",
                side_effect=lambda name, *a, **kw: (
                    (_ for _ in ()).throw(ImportError(name))
                    if name == "multi_memory"
                    else __builtins__.__import__(name, *a, **kw)
                ),
            ),
        ):
            _cmd_status(args)
        out = capsys.readouterr().out
        assert "unknown" in out

    def test_status_json_version_import_fail(self, capsys):
        """JSON status handles ImportError for version."""
        config = {"memory": {}}
        args = argparse.Namespace(json_output=True)
        with (
            mock.patch("multi_memory.cli.load_config", return_value=config),
            mock.patch(
                "builtins.__import__",
                side_effect=lambda name, *a, **kw: (
                    (_ for _ in ()).throw(ImportError(name))
                    if name == "multi_memory"
                    else __builtins__.__import__(name, *a, **kw)
                ),
            ),
        ):
            _cmd_status(args)
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["version"] == "unknown"

    def test_status_legacy_provider_not_installed(self, capsys):
        """Legacy provider not in active and not installed shows normal display."""
        config = {
            "memory": {
                "provider": "someoldprovider",
            }
        }
        args = argparse.Namespace(json_output=False)
        with mock.patch("multi_memory.cli.load_config", return_value=config):
            _cmd_status(args)
        out = capsys.readouterr().out
        assert "someoldprovider" in out


# ── _cmd_add edge cases ──────────────────────────────────────────────────


class TestCmdAddEdgeCases:
    def test_add_unknown_backend(self, capsys):
        """Add with unknown backend name prints error."""
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
        with (
            mock.patch("multi_memory.cli.load_config", return_value=config),
            mock.patch("multi_memory.cli.save_config", side_effect=saved.update),
        ):
            _cmd_add(args)
        out = capsys.readouterr().out
        assert "Added" in out
        assert saved["memory"]["multi"]["backends"]["mem0"] == {}


# ── _cmd_remove edge cases ───────────────────────────────────────────────


class TestCmdRemoveEdgeCases:
    def test_remove_with_remaining(self, capsys):
        """Remove one of two backends shows remaining."""
        config = {
            "memory": {
                "provider": "multi",
                "multi": {"backends": {"mem0": {}, "holographic": {}}},
                "providers": ["mem0", "holographic"],
            }
        }
        args = argparse.Namespace(backend="mem0")
        with (
            mock.patch("multi_memory.cli.load_config", return_value=config),
            mock.patch("multi_memory.cli.save_config"),
        ):
            _cmd_remove(args)
        out = capsys.readouterr().out
        assert "Removed" in out
        assert "holographic" in out

    def test_remove_non_dict_memory_cfg(self, capsys):
        """Remove with non-dict memory config shows error."""
        args = argparse.Namespace(backend="mem0")
        with mock.patch("multi_memory.cli.load_config", return_value={}):
            _cmd_remove(args)
        out = capsys.readouterr().out
        assert "No memory config found" in out
