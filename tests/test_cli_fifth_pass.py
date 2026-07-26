"""Tests for fifth-pass CLI features: --check, --force, --all, --config-only, categorized list."""

from __future__ import annotations

import argparse
import json
from unittest import mock

from multi_memory.cli import (
    _cmd_add,
    _cmd_list,
    _cmd_remove,
    _cmd_update,
    _cmd_update_check,
    multi_command,
)


class TestUpdateCheck:
    """hermes multi update --check."""

    def test_check_shows_version(self, capsys):
        args = argparse.Namespace(check=True)
        with mock.patch("multi_memory.cli.subprocess.run") as mock_run:
            mock_run.return_value = mock.MagicMock(returncode=0, stdout="multi 0.13.0\nlatest")
            _cmd_update(args)
        out = capsys.readouterr().out
        assert "Current version" in out
        assert "Checking" in out

    def test_check_hermes_not_found(self, capsys):
        args = argparse.Namespace(check=True)
        with mock.patch("multi_memory.cli.subprocess.run", side_effect=FileNotFoundError):
            _cmd_update(args)
        out = capsys.readouterr().out
        assert "not found" in out

    def test_check_timeout(self, capsys):
        import subprocess

        args = argparse.Namespace(check=True)
        with mock.patch(
            "multi_memory.cli.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="hermes", timeout=30),
        ):
            _cmd_update(args)
        out = capsys.readouterr().out
        assert "timed out" in out

    def test_check_generic_error(self, capsys):
        args = argparse.Namespace(check=True)
        with mock.patch("multi_memory.cli.subprocess.run", side_effect=OSError("boom")):
            _cmd_update(args)
        out = capsys.readouterr().out
        assert "Check failed" in out

    def test_check_no_output(self, capsys):
        args = argparse.Namespace(check=True)
        with mock.patch("multi_memory.cli.subprocess.run") as mock_run:
            mock_run.return_value = mock.MagicMock(returncode=1, stdout="")
            _cmd_update(args)
        out = capsys.readouterr().out
        assert "Could not fetch" in out

    def test_update_check_helper_directly(self, capsys):
        """_cmd_update_check can be called directly."""
        with mock.patch("multi_memory.cli.subprocess.run") as mock_run:
            mock_run.return_value = mock.MagicMock(returncode=0, stdout="info")
            _cmd_update_check()
        out = capsys.readouterr().out
        assert "Current version" in out


class TestRemoveForce:
    """hermes multi remove --force skips confirmation."""

    def test_remove_force_skips_prompt(self, capsys):
        config = {"memory": {"multi": {"backends": {"mem0": {}}}, "providers": ["mem0"]}}
        args = argparse.Namespace(backend="mem0", force=True)
        with (
            mock.patch("multi_memory.cli.load_config", return_value=config),
            mock.patch("multi_memory.cli.save_config"),
        ):
            _cmd_remove(args)
        out = capsys.readouterr().out
        assert "Removed" in out

    def test_remove_no_force_confirms_yes(self, capsys):
        config = {"memory": {"multi": {"backends": {"mem0": {}}}, "providers": ["mem0"]}}
        args = argparse.Namespace(backend="mem0", force=False)
        with (
            mock.patch("multi_memory.cli.load_config", return_value=config),
            mock.patch("multi_memory.cli.save_config"),
            mock.patch("builtins.input", return_value="y"),
        ):
            _cmd_remove(args)
        out = capsys.readouterr().out
        assert "Removed" in out

    def test_remove_no_force_confirms_no(self, capsys):
        config = {"memory": {"multi": {"backends": {"mem0": {}}}, "providers": ["mem0"]}}
        args = argparse.Namespace(backend="mem0", force=False)
        with (
            mock.patch("multi_memory.cli.load_config", return_value=config),
            mock.patch("builtins.input", return_value="n"),
        ):
            _cmd_remove(args)
        out = capsys.readouterr().out
        assert "Cancelled" in out

    def test_remove_no_force_eof(self, capsys):
        config = {"memory": {"multi": {"backends": {"mem0": {}}}, "providers": ["mem0"]}}
        args = argparse.Namespace(backend="mem0", force=False)
        with (
            mock.patch("multi_memory.cli.load_config", return_value=config),
            mock.patch("builtins.input", side_effect=EOFError),
        ):
            _cmd_remove(args)
        out = capsys.readouterr().out
        assert "Cancelled" in out


class TestListCategorized:
    """hermes multi list with BACKEND_CATEGORIES."""

    def test_list_shows_categories(self, capsys):
        args = argparse.Namespace(json_output=False, show_all=False)
        with mock.patch("multi_memory.cli.load_config", return_value={}):
            _cmd_list(args)
        out = capsys.readouterr().out
        assert "Local" in out
        assert "Cloud" in out

    def test_list_json_includes_category(self, capsys):
        args = argparse.Namespace(json_output=True, show_all=False)
        with mock.patch("multi_memory.cli.load_config", return_value={}):
            _cmd_list(args)
        out = capsys.readouterr().out
        data = json.loads(out)
        assert all("category" in row for row in data)
        categories = {row["category"] for row in data}
        assert "local" in categories
        assert "cloud" in categories

    def test_list_all_flag(self, capsys):
        args = argparse.Namespace(json_output=False, show_all=True)
        with mock.patch("multi_memory.cli.load_config", return_value={}):
            _cmd_list(args)
        out = capsys.readouterr().out
        assert "--all" in out


class TestAddConfigOnly:
    """hermes multi add --config-only skips dependency installation."""

    def test_add_config_only_skips_install(self, capsys):
        config = {"memory": {}}
        args = argparse.Namespace(backend="mem0", config_only=True)
        with (
            mock.patch("multi_memory.cli.load_config", return_value=config),
            mock.patch("multi_memory.cli.save_config"),
            mock.patch("multi_memory.cli._install_dependencies") as mock_install,
        ):
            _cmd_add(args)
        mock_install.assert_not_called()
        out = capsys.readouterr().out
        assert "Added" in out

    def test_add_without_config_only_installs(self, capsys):
        config = {"memory": {}}
        args = argparse.Namespace(backend="mem0", config_only=False)
        with (
            mock.patch("multi_memory.cli.load_config", return_value=config),
            mock.patch("multi_memory.cli.save_config"),
            mock.patch("multi_memory.cli._install_dependencies") as mock_install,
        ):
            _cmd_add(args)
        mock_install.assert_called_once_with("mem0")


class TestMultiCommandDispatch:
    """multi_command routes validate and update correctly."""

    def test_dispatch_validate(self):
        args = argparse.Namespace(multi_command="validate", fix=False)
        with mock.patch("multi_memory.cli._cmd_validate") as mock_validate:
            multi_command(args)
        mock_validate.assert_called_once_with(args)

    def test_dispatch_update(self):
        args = argparse.Namespace(multi_command="update", check=False)
        with mock.patch("multi_memory.cli._cmd_update") as mock_update:
            multi_command(args)
        mock_update.assert_called_once_with(args)
