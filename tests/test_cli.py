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
        """register_cli adds status/list/add/remove subcommands."""
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
        with mock.patch("multi_memory.cli.load_config", return_value=config):
            _cmd_status(args)
        out = capsys.readouterr().out
        assert "2 active backend" in out
        assert "mnemosyne" in out
        assert "holographic" in out

    def test_status_providers_list_format(self, capsys):
        """status handles providers list format."""
        config = {"memory": {"providers": ["mem0", "honcho"]}}
        args = argparse.Namespace(json_output=False)
        with mock.patch("multi_memory.cli.load_config", return_value=config):
            _cmd_status(args)
        out = capsys.readouterr().out
        assert "2 active backend" in out
        assert "mem0" in out

    def test_status_json(self, capsys):
        """status --json outputs valid JSON."""
        config = {"memory": {"multi": {"backends": {"mnemosyne": {}}}}}
        args = argparse.Namespace(json_output=True)
        with mock.patch("multi_memory.cli.load_config", return_value=config):
            _cmd_status(args)
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["provider"] == "multi"
        assert "mnemosyne" in data["active_backends"]

    def test_status_empty(self, capsys):
        """status with no backends shows empty message."""
        config = {"memory": {}}
        args = argparse.Namespace(json_output=False)
        with mock.patch("multi_memory.cli.load_config", return_value=config):
            _cmd_status(args)
        out = capsys.readouterr().out
        assert "No backends configured" in out


# ── list ──────────────────────────────────────────────────────────────────

class TestCmdList:
    def test_list_shows_all_backends(self, capsys):
        """list shows all 9 known backends."""
        config = {"memory": {}}
        args = argparse.Namespace(json_output=False)
        with mock.patch("multi_memory.cli.load_config", return_value=config):
            _cmd_list(args)
        out = capsys.readouterr().out
        for name in ["mnemosyne", "holographic", "mem0", "honcho",
                      "openviking", "hindsight", "retaindb", "byterover",
                      "supermemory"]:
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
        with mock.patch("multi_memory.cli.load_config", return_value=config), \
             mock.patch("multi_memory.cli.save_config", side_effect=saved.update):
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


# ── remove ────────────────────────────────────────────────────────────────

class TestCmdRemove:
    def test_remove_existing(self, capsys):
        """remove deletes backend from config."""
        config = {"memory": {"multi": {"backends": {"mem0": {}}}, "providers": ["mem0"]}}
        saved = {}
        args = argparse.Namespace(backend="mem0")
        with mock.patch("multi_memory.cli.load_config", return_value=config), \
             mock.patch("multi_memory.cli.save_config", side_effect=saved.update):
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
        """remove last backend shows built-in only message."""
        config = {
            "memory": {
                "multi": {"backends": {"mem0": {}}},
                "providers": ["mem0"],
                "provider": "mem0",
            }
        }
        saved = {}
        args = argparse.Namespace(backend="mem0")
        with mock.patch("multi_memory.cli.load_config", return_value=config), \
             mock.patch("multi_memory.cli.save_config", side_effect=saved.update):
            _cmd_remove(args)
        out = capsys.readouterr().out
        assert "built-in only" in out
