"""Tests for API parity with the latest Hermes MemoryProvider ABC.

Covers:
- backup_paths() forwarding and merge/dedupe on MultiMemoryProvider
- backup_paths() forwarding on _SubProviderAdapter
- rewound parameter forwarded through on_session_switch
- JSON error contract on handle_tool_call fallback
- Standalone stub has all ABC methods
- _batch_shutdown concurrent behaviour
- Budget threshold applied from single config read
"""

# intentional imports-inside-functions + magic numbers in tests
from __future__ import annotations

import json
import time
from unittest import mock

from multi_memory import MultiMemoryProvider
from multi_memory.adapters import _SubProviderAdapter

# ── backup_paths on MultiMemoryProvider ────────────────────────────────────


class TestBackupPaths:
    """MultiMemoryProvider.backup_paths() merges and deduplicates sub paths."""

    def _provider_with_subs(self, *path_lists):
        p = MultiMemoryProvider()
        p._subs = []
        for i, paths in enumerate(path_lists):
            sub = mock.MagicMock()
            sub.name = f"sub{i}"
            sub.backup_paths.return_value = paths
            p._subs.append(sub)
        return p

    def test_empty_subs_returns_empty(self):
        p = MultiMemoryProvider()
        p._subs = []
        assert p.backup_paths() == []

    def test_single_sub_paths(self):
        p = self._provider_with_subs(["/home/.honcho", "/home/.hindsight"])
        assert p.backup_paths() == ["/home/.honcho", "/home/.hindsight"]

    def test_merge_multiple_subs(self):
        p = self._provider_with_subs(
            ["/home/.honcho"],
            ["/home/.hindsight", "/home/.openviking"],
        )
        assert p.backup_paths() == ["/home/.honcho", "/home/.hindsight", "/home/.openviking"]

    def test_deduplicates(self):
        p = self._provider_with_subs(
            ["/home/.honcho", "/shared"],
            ["/home/.hindsight", "/shared"],
        )
        result = p.backup_paths()
        assert result.count("/shared") == 1
        assert "/home/.honcho" in result
        assert "/home/.hindsight" in result

    def test_sub_without_backup_paths_method(self):
        """Sub that has no backup_paths method is skipped gracefully."""
        p = MultiMemoryProvider()
        sub = mock.MagicMock(spec=[])  # no attributes
        sub.name = "bare"
        p._subs = [sub]
        assert p.backup_paths() == []

    def test_sub_backup_paths_exception_isolated(self):
        """One sub raising doesn't block others."""
        p = MultiMemoryProvider()
        bad = mock.MagicMock()
        bad.name = "bad"
        bad.backup_paths.side_effect = RuntimeError("boom")
        good = mock.MagicMock()
        good.name = "good"
        good.backup_paths.return_value = ["/good/path"]
        p._subs = [bad, good]
        assert p.backup_paths() == ["/good/path"]

    def test_order_preserved(self):
        p = self._provider_with_subs(["/c", "/a"], ["/b", "/a"])
        assert p.backup_paths() == ["/c", "/a", "/b"]


# ── backup_paths on _SubProviderAdapter ────────────────────────────────────


class TestAdapterBackupPaths:
    """_SubProviderAdapter.backup_paths() forwards to delegate."""

    def _make_adapter(self, delegate):
        adapter = _SubProviderAdapter.__new__(_SubProviderAdapter)
        adapter._delegate = delegate
        adapter._cached_write_mode = None
        adapter._cached_accepts_messages = None
        return adapter

    def test_forwards_to_delegate(self):
        delegate = mock.MagicMock()
        delegate.backup_paths.return_value = ["/ext/path"]
        adapter = self._make_adapter(delegate)
        assert adapter.backup_paths() == ["/ext/path"]

    def test_no_backup_paths_method_returns_empty(self):
        delegate = mock.MagicMock(spec=[])  # no backup_paths
        adapter = self._make_adapter(delegate)
        assert adapter.backup_paths() == []

    def test_returns_copy(self):
        """Returned list is a copy — mutations don't affect the delegate."""
        delegate = mock.MagicMock()
        delegate.backup_paths.return_value = ["/a"]
        adapter = self._make_adapter(delegate)
        result = adapter.backup_paths()
        result.append("/mutated")
        assert delegate.backup_paths.return_value == ["/a"]


# ── rewound parameter on on_session_switch ─────────────────────────────────


class TestRewoundForwarding:
    """on_session_switch forwards rewound kwarg to all subs."""

    def test_rewound_forwarded(self):
        p = MultiMemoryProvider()
        sub = mock.MagicMock()
        sub.name = "test"
        p._subs = [sub]
        p.on_session_switch("new-sid", parent_session_id="old-sid", reset=False, rewound=True)
        sub.on_session_switch.assert_called_once()
        _, kwargs = sub.on_session_switch.call_args
        assert kwargs["rewound"] is True

    def test_rewound_defaults_false(self):
        p = MultiMemoryProvider()
        sub = mock.MagicMock()
        sub.name = "test"
        p._subs = [sub]
        p.on_session_switch("new-sid")
        _, kwargs = sub.on_session_switch.call_args
        assert kwargs.get("rewound", False) is False

    def test_empty_session_id_skips(self):
        p = MultiMemoryProvider()
        sub = mock.MagicMock()
        sub.name = "test"
        p._subs = [sub]
        p.on_session_switch("")
        sub.on_session_switch.assert_not_called()


# ── JSON error contract on handle_tool_call ────────────────────────────────


class TestHandleToolCallErrorContract:
    """handle_tool_call fallback returns valid JSON per Hermes tool_error contract."""

    def test_unmatched_tool_returns_valid_json(self):
        p = MultiMemoryProvider()
        p._subs = []
        result = p.handle_tool_call("nonexistent_tool", {})
        parsed = json.loads(result)  # must not raise
        assert "error" in parsed

    def test_unmatched_tool_json_contains_tool_name(self):
        p = MultiMemoryProvider()
        p._subs = []
        result = p.handle_tool_call("ghost_tool", {})
        parsed = json.loads(result)
        assert "ghost_tool" in parsed["error"]

    def test_fallback_all_subs_fail_returns_json(self):
        """When prefix match fails and all subs raise, error is still JSON."""
        p = MultiMemoryProvider()
        sub = mock.MagicMock()
        sub.name = "broken"
        sub.handle_tool_call.side_effect = RuntimeError("kaboom")
        # PREFIX doesn't match tool name, so it falls through to fallback loop
        type(sub).PREFIX = "zzz"
        p._subs = [sub]
        result = p.handle_tool_call("unmatched_tool", {})
        parsed = json.loads(result)
        assert "error" in parsed
        assert "kaboom" in parsed["error"]


# ── Standalone stub parity ─────────────────────────────────────────────────


class TestStandaloneStubParity:
    """The standalone MemoryProvider stub exposes all ABC methods."""

    def _get_stub_class(self):
        """Import the standalone stub by forcing ImportError on agent.memory_provider."""
        import importlib
        import sys

        # Save and remove agent.memory_provider so the ImportError path triggers
        saved = {}
        for key in list(sys.modules):
            if key.startswith("agent"):
                saved[key] = sys.modules.pop(key)

        # Also remove multi_memory so it re-imports fresh
        for key in list(sys.modules):
            if key.startswith("multi_memory"):
                saved[key] = sys.modules.pop(key)

        try:
            import multi_memory as mm_fresh

            importlib.reload(mm_fresh)
            # The stub is the MemoryProvider that multi_memory imported
            stub = mm_fresh.MemoryProvider
            return stub
        finally:
            # Restore all saved modules
            for key in list(sys.modules):
                if key.startswith("multi_memory"):
                    sys.modules.pop(key, None)
            sys.modules.update(saved)

    def _concrete_stub(self, stub_cls):
        """Create a concrete subclass of the stub ABC for instantiation."""
        concrete = type(
            "_Concrete",
            (stub_cls,),
            {
                "name": "test",
                "is_available": lambda self: True,
                "initialize": lambda self, session_id, **kw: None,
                "get_tool_schemas": lambda self: [],
                "handle_tool_call": lambda self, tool_name, args, **kw: "",
            },
        )
        return concrete()

    def test_stub_has_backup_paths(self):
        stub = self._get_stub_class()
        assert hasattr(stub, "backup_paths")
        instance = self._concrete_stub(stub)
        assert instance.backup_paths() == []

    def test_stub_has_get_config_schema(self):
        stub = self._get_stub_class()
        assert hasattr(stub, "get_config_schema")
        instance = self._concrete_stub(stub)
        assert instance.get_config_schema() == []

    def test_stub_has_save_config(self):
        stub = self._get_stub_class()
        assert hasattr(stub, "save_config")

    def test_stub_on_session_switch_accepts_rewound(self):
        stub = self._get_stub_class()
        import inspect

        sig = inspect.signature(stub.on_session_switch)
        assert "rewound" in sig.parameters


# ── _batch_shutdown ────────────────────────────────────────────────────────


class TestBatchShutdown:
    """_batch_shutdown runs subs concurrently with timeout."""

    def test_all_subs_closed(self):
        from multi_memory import _batch_shutdown

        closed = []
        subs = []
        for name in ("a", "b", "c"):
            sub = mock.MagicMock()
            sub.name = name
            sub.close = lambda n=name: closed.append(n)
            subs.append(sub)
        _batch_shutdown(subs)
        assert sorted(closed) == ["a", "b", "c"]

    def test_close_called_on_adapter(self):
        """_close_one calls sub.close() — the adapter handles the shutdown fallback."""
        from multi_memory import _batch_shutdown

        closed = []
        sub = mock.MagicMock()
        sub.name = "x"
        sub.close = lambda: closed.append("x")
        _batch_shutdown([sub])
        assert closed == ["x"]

    def test_timeout_abandoned(self, caplog):
        from multi_memory import _batch_shutdown

        sub = mock.MagicMock()
        sub.name = "slow"

        def hang():
            time.sleep(5)

        sub.close = hang
        with caplog.at_level("WARNING", logger="multi_memory"):
            _batch_shutdown([sub], timeout=0.1)
        assert any("timed out" in r.getMessage() for r in caplog.records)

    def test_exception_isolated(self, caplog):
        from multi_memory import _batch_shutdown

        good_called = []
        bad = mock.MagicMock()
        bad.name = "bad"
        bad.close = mock.MagicMock(side_effect=RuntimeError("oops"))
        good = mock.MagicMock()
        good.name = "good"
        good.close = lambda: good_called.append("good")
        with caplog.at_level("WARNING", logger="multi_memory"):
            _batch_shutdown([bad, good])
        assert "good" in good_called
        assert any("oops" in r.getMessage() for r in caplog.records)


# ── Budget threshold from single config read ───────────────────────────────


class TestBudgetThresholdSingleRead:
    """Budget threshold is applied during _load_config, not a separate read."""

    def test_threshold_applied_from_config(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("memory:\n  multi:\n    tool_budget_threshold: 99\n    backends: {}\n")
        with mock.patch("multi_memory.config._get_config_path", return_value=str(cfg)):
            p = MultiMemoryProvider()
        assert p._tool_budget.threshold == 99

    def test_threshold_default_when_absent(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("memory:\n  multi:\n    backends: {}\n")
        with mock.patch("multi_memory.config._get_config_path", return_value=str(cfg)):
            p = MultiMemoryProvider()
        from multi_memory.budget import DEFAULT_THRESHOLD

        assert p._tool_budget.threshold == DEFAULT_THRESHOLD

    def test_no_second_config_read(self, tmp_path):
        """Config file is opened exactly once during __init__."""
        cfg = tmp_path / "config.yaml"
        cfg.write_text("memory:\n  multi:\n    tool_budget_threshold: 5\n    backends: {}\n")
        open_count = [0]
        original_open = open

        def counting_open(*args, **kwargs):
            if str(args[0]) == str(cfg):
                open_count[0] += 1
            return original_open(*args, **kwargs)

        with (
            mock.patch("multi_memory.config._get_config_path", return_value=str(cfg)),
            mock.patch("builtins.open", side_effect=counting_open),
        ):
            MultiMemoryProvider()
        assert open_count[0] == 1, f"config.yaml opened {open_count[0]} times, expected 1"
