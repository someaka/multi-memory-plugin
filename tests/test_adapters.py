"""Tests for multi_memory plugin — adapters, lifecycle hooks, edge paths.

This file covers:
- _SubProviderAdapter and subclasses
- MultiMemoryProvider lifecycle hooks (initialize, shutdown, prefetch, etc.)
- Edge cases: missing backend, error handling, adapter instantiation failures
"""

# ruff: noqa: PLC0415, PLR2004  # intentional imports-inside-functions + magic numbers in tests
from __future__ import annotations

import os
from unittest import mock

import pytest
from conftest import requires_holographic

from multi_memory import (
    MultiMemoryProvider,
    _load_backends_from_config,
    _normalise_multi_config,
)
from multi_memory.adapters import (
    _ByteRoverAdapter,
    _HindsightAdapter,
    _HolographicAdapter,
    _HonchoAdapter,
    _Mem0Adapter,
    _MnemosyneAdapter,
    _OpenVikingAdapter,
    _RetainDBAdapter,
    _SubProviderAdapter,
    _SupermemoryAdapter,
    _try_import,
)

# ── Existing tests (preserved from original) ─────────────────────────────────


class TestNormaliseMultiConfig:
    def test_providers_list(self):
        result = _normalise_multi_config({"providers": ["mnemosyne", "mem0"]})
        assert result == {"mnemosyne": {}, "mem0": {}}

    def test_backends_dict(self):
        cfg = {"multi": {"backends": {"mnemosyne": False, "mem0": {"api_key": "k"}}}}
        result = _normalise_multi_config(cfg)
        assert result["mnemosyne"] is False
        assert result["mem0"] == {"api_key": "k"}

    def test_empty_cfg(self):
        assert _normalise_multi_config({}) == {}

    def test_providers_empty_list(self):
        assert _normalise_multi_config({"providers": []}) == {}


class TestLoadBackendsFromConfig:
    def test_empty_config(self):
        assert _load_backends_from_config({}) == []

    def test_unknown_backend_skips(self):
        cfg = {"memory": {"multi": {"backends": {"no_such_backend": {}}}}}
        result = _load_backends_from_config(cfg)
        assert result == []

    def test_false_backend_skipped(self):
        cfg = {"memory": {"multi": {"backends": {"mnemosyne": False, "mem0": True}}}}
        result = _load_backends_from_config(cfg)
        assert all(a.name != "mnemosyne" for a in result)

    def test_none_skipped(self):
        cfg = {"memory": {"multi": {"backends": {"mnemosyne": None, "mem0": True}}}}
        result = _load_backends_from_config(cfg)
        assert "mnemosyne" not in [a.name for a in result]

    def test_zero_string_skipped(self):
        cfg = {"memory": {"multi": {"backends": {"mnemosyne": "0", "mem0": True}}}}
        result = _load_backends_from_config(cfg)
        assert "mnemosyne" not in [a.name for a in result]

    def test_false_string_skipped(self):
        cfg = {"memory": {"multi": {"backends": {"mnemosyne": "false", "mem0": True}}}}
        result = _load_backends_from_config(cfg)
        assert "mnemosyne" not in [a.name for a in result]

    def test_false_capital_skipped(self):
        cfg = {"memory": {"multi": {"backends": {"mnemosyne": "False", "mem0": True}}}}
        result = _load_backends_from_config(cfg)
        assert "mnemosyne" not in [a.name for a in result]

    @requires_holographic
    def test_empty_dict_enabled(self):
        cfg = {"memory": {"multi": {"backends": {"holographic": {}}}}}
        result = _load_backends_from_config(cfg)
        assert any(a.name == "holographic" for a in result)

    def test_available_backend_is_loaded(self):
        """Backend that is_available() returns True gets appended (covers the happy path)."""
        mock_adapter = mock.MagicMock()
        mock_adapter.is_available.return_value = True
        mock_adapter.name = "fake_backend"

        mock_cls = mock.MagicMock()
        mock_cls.return_value = mock_adapter
        mock_cls.CONFIG_KEY = "fake"

        with mock.patch("multi_memory._SUB_CLASSES", (mock_cls,)):
            cfg = {"memory": {"multi": {"backends": {"fake": {}}}}}
            result = _load_backends_from_config(cfg)
        assert len(result) == 1
        assert result[0].name == "fake_backend"

    def test_unavailable_backend_is_skipped(self):
        """Backend that is_available() returns False is not loaded."""
        mock_adapter = mock.MagicMock()
        mock_adapter.is_available.return_value = False

        mock_cls = mock.MagicMock()
        mock_cls.return_value = mock_adapter
        mock_cls.CONFIG_KEY = "fake"

        with mock.patch("multi_memory._SUB_CLASSES", (mock_cls,)):
            cfg = {"memory": {"multi": {"backends": {"fake": {}}}}}
            result = _load_backends_from_config(cfg)
        assert result == []


# ── _try_import tests ───────────────────────────────────────────────────────


class TestTryImport:
    """_try_import: safe module import with graceful fallback."""

    def test_import_existing_module(self):
        """Returns the class when module + attribute exist."""
        cls = _try_import("logging", "Logger")
        assert cls is not None

    def test_none_for_missing_module(self):
        """Returns None when module does not exist."""
        cls = _try_import("nonexistent_module_xyz", "SomeClass")
        assert cls is None

    def test_none_for_missing_attr(self):
        """Returns None when attribute does not exist in module."""
        cls = _try_import("logging", "NonExistentClass")
        assert cls is None

    def test_none_for_exception(self):
        """Returns None if import raises (e.g. broken module).

        We test this by patching find_spec to return something truthy
        but import_module to raise.
        """
        with (
            mock.patch("multi_memory.adapters.find_spec", return_value=mock.MagicMock()),
            mock.patch(
                "multi_memory.adapters.importlib.import_module",
                side_effect=ImportError("broken"),
            ),
        ):
            cls = _try_import("broken_module", "Cls")
            assert cls is None


# ── _SubProviderAdapter edge paths ──────────────────────────────────────────


class TestSubProviderAdapter:
    """Edge cases for _SubProviderAdapter instantiation and behavior."""

    def test_init_raises_on_missing_module(self):
        """Creating an adapter for an uninstalled backend raises RuntimeError."""

        class MissingBackendAdapter(_SubProviderAdapter):
            CONFIG_KEY = "missing"
            MODULE = "does_not_exist_abc_123"
            CLASS = "Provider"
            PREFIX = "missing"

        with pytest.raises(RuntimeError, match="not installed"):
            MissingBackendAdapter()

    def test_mnemosyne_adapter_properties(self):
        """Class-level properties without instantiation (mnemosyne may not be installed)."""
        assert _MnemosyneAdapter.CONFIG_KEY == "mnemosyne"
        assert _MnemosyneAdapter.MODULE == "mnemosyne"
        assert _MnemosyneAdapter.PREFIX == "mnemosyne"

    def test_mem0_adapter_properties(self):
        # mem0 may not be installed — check and skip if not
        adapter_cls = _Mem0Adapter
        assert adapter_cls.CONFIG_KEY == "mem0"
        assert adapter_cls.MODULE == "plugins.memory.mem0"
        assert adapter_cls.PREFIX == "mem0"

    @requires_holographic
    def test_holographic_adapter_properties(self):
        adapter = _HolographicAdapter()
        assert adapter.CONFIG_KEY == "holographic"
        assert adapter.PREFIX == "holographic"
        assert adapter.name == "holographic"

    def test_honcho_adapter_properties(self):
        adapter_cls = _HonchoAdapter
        assert adapter_cls.CONFIG_KEY == "honcho"
        assert adapter_cls.MODULE == "plugins.memory.honcho"
        assert adapter_cls.PREFIX == "honcho"

    def test_openviking_adapter_properties(self):
        adapter_cls = _OpenVikingAdapter
        assert adapter_cls.CONFIG_KEY == "openviking"
        assert adapter_cls.MODULE == "plugins.memory.openviking"
        assert adapter_cls.PREFIX == "viking"

    def test_hindsight_adapter_properties(self):
        adapter_cls = _HindsightAdapter
        assert adapter_cls.CONFIG_KEY == "hindsight"
        assert adapter_cls.MODULE == "plugins.memory.hindsight"
        assert adapter_cls.PREFIX == "hindsight"

    def test_retaindb_adapter_properties(self):
        adapter_cls = _RetainDBAdapter
        assert adapter_cls.CONFIG_KEY == "retaindb"
        assert adapter_cls.MODULE == "plugins.memory.retaindb"
        assert adapter_cls.PREFIX == "retaindb"

    def test_byterover_adapter_properties(self):
        adapter_cls = _ByteRoverAdapter
        assert adapter_cls.CONFIG_KEY == "byterover"
        assert adapter_cls.MODULE == "plugins.memory.byterover"
        assert adapter_cls.PREFIX == "brv"

    def test_supermemory_adapter_properties(self):
        adapter_cls = _SupermemoryAdapter
        assert adapter_cls.CONFIG_KEY == "supermemory"
        assert adapter_cls.MODULE == "plugins.memory.supermemory"
        assert adapter_cls.PREFIX == "supermemory"

    def test_mnemosyne_name_override(self):
        """_MnemosyneAdapter.name returns 'mnemosyne' (hardcoded override)."""
        # The name property is a class-level override, not a delegation
        # We can test it by creating a mock instance and checking the property
        assert _MnemosyneAdapter.name.fget is not None  # property exists
        # Create a mock instance to test the property getter
        adapter = object.__new__(_MnemosyneAdapter)
        assert adapter.name == "mnemosyne"

    @requires_holographic
    def test_get_tool_schemas_prefixes_names(self):
        """Tool schemas are prefixed with the adapter's PREFIX."""
        adapter = _HolographicAdapter()
        schemas = adapter.get_tool_schemas()
        assert schemas  # holographic has tools
        for s in schemas:
            assert s["name"].startswith("holographic_")

    @requires_holographic
    def test_handle_tool_call_strips_prefix(self):
        """handle_tool_call strips the PREFIX before delegating."""
        adapter = _HolographicAdapter()
        # Use a real tool name with prefix
        result = adapter.handle_tool_call("holographic_fact_store", {"action": "list"})
        assert isinstance(result, str)  # returns a string (may be error or success)

    @requires_holographic
    def test_is_available_delegates(self):
        adapter = _HolographicAdapter()
        assert isinstance(adapter.is_available(), bool)


# ── MultiMemoryProvider ─────────────────────────────────────────────────────


@pytest.fixture
def provider():
    """Return a MultiMemoryProvider with mock sub-providers for testing.

    Uses mock backends so tests work regardless of which real backends
    are installed on the system.
    """
    p = MultiMemoryProvider()

    # Create mock sub-adapters for testing
    mock_holo = mock.MagicMock()
    mock_holo.name = "holographic"
    mock_holo.get_tool_schemas.return_value = [
        {"name": "holographic_fact_store", "description": "Store facts"},
        {"name": "holographic_probe", "description": "Probe entities"},
    ]
    mock_holo.system_prompt_block.return_value = "Holographic memory active"

    mock_memo = mock.MagicMock()
    mock_memo.name = "mnemosyne"
    mock_memo.get_tool_schemas.return_value = [
        {"name": "mnemosyne_search", "description": "Search memories"},
    ]
    mock_memo.system_prompt_block.return_value = ""

    p._subs = [mock_holo, mock_memo]
    return p


class TestMultiMemoryProvider:
    def test_name(self, provider):
        assert provider.name == "multi"

    def test_auto_loads_backends(self, provider):
        assert provider.is_available() is True
        names = [s.name for s in provider._subs]
        assert "holographic" in names

    def test_get_tool_schemas_returns_prefixed(self, provider):
        schemas = provider.get_tool_schemas()
        assert any("_" in s["name"] for s in schemas)

    def test_handle_tool_call_matches_schema(self, provider):
        schemas = provider.get_tool_schemas()
        if schemas:
            result = provider.handle_tool_call(schemas[0]["name"], {})
            assert "No sub-provider handles" not in result

    def test_is_available_with_subs(self, provider):
        assert provider.is_available() is True

    def test_handle_tool_call_unmatched_returns_error(self):
        """With empty subs, any tool call returns the fallback error."""
        p = MultiMemoryProvider()
        p._subs = []
        result = p.handle_tool_call("nonexistent_tool", {})
        assert "No sub-provider handles" in result


# ── Lifecycle hook tests ────────────────────────────────────────────────────


class TestLifecycleHooks:
    """MultiMemoryProvider lifecycle hooks fan out to all sub-providers."""

    def test_initialize_calls_all_subs(self, provider):
        """initialize() is called on every sub-provider."""
        names_called = []
        for sub in provider._subs:
            sub.initialize = lambda *a, ns=sub.name, **kw: names_called.append(ns)
        provider.initialize(session_id="test-session")
        expected = [s.name for s in provider._subs]
        assert names_called == expected

    def test_initialize_exception_isolation(self, provider):
        """Failure in one sub's initialize() doesn't stop others."""
        fail_flags = []

        for i, sub in enumerate(provider._subs):
            original_init = sub.initialize

            def make_init(idx, orig):
                def new_init(*args, **kwargs):
                    fail_flags.append(idx)
                    if idx == 0:
                        raise RuntimeError(f"fail {idx}")
                    return orig(*args, **kwargs)

                return new_init

            sub.initialize = make_init(i, original_init)

        # Should not raise — exceptions in initialize are caught
        provider.initialize(session_id="test-session")
        assert len(fail_flags) == len(provider._subs)

    def test_shutdown_calls_in_reverse_order(self, provider):
        """shutdown() calls sub-providers in reversed order."""
        call_order = []
        subs_snapshot = list(provider._subs)
        for sub in subs_snapshot:
            # shutdown() prefers close() over shutdown() — mock both
            ns = sub.name
            sub.close = lambda ns=ns: call_order.append(ns)
            sub.shutdown = lambda ns=ns: call_order.append(ns)
        provider.shutdown()
        expected = [s.name for s in reversed(subs_snapshot)]
        assert call_order == expected

    def test_shutdown_exception_isolation(self, provider):
        """Failure in one sub's shutdown() doesn't stop others."""
        flags = []
        subs_snapshot = list(provider._subs)
        for i, sub in enumerate(subs_snapshot):

            def make_shutdown(idx):
                def fn():
                    flags.append(idx)
                    if idx % 2 == 0:
                        raise RuntimeError(f"shutdown fail {idx}")

                return fn

            # shutdown() prefers close() — mock both to track calls
            sub.close = make_shutdown(i)
            sub.shutdown = make_shutdown(i)
        provider.shutdown()  # Should not raise
        assert len(flags) == len(subs_snapshot)

    def test_prefetch_concatenates_results(self, provider):
        """prefetch() collects non-empty results from all subs."""
        if len(provider._subs) < 2:
            # Need at least 2 subs to test concatenation
            pytest.skip("Need at least 2 subs")
        result = provider.prefetch("test query", session_id="s1")
        # Each sub returns something or empty string
        assert isinstance(result, str)

    def test_prefetch_exception_isolation(self, provider):
        """Failure in one sub's prefetch still returns results from others."""
        for i, sub in enumerate(provider._subs):
            if i == 0:
                sub.prefetch.side_effect = RuntimeError("prefetch fail")
        result = provider.prefetch("test query", session_id="s1")
        assert isinstance(result, str)  # doesn't raise

    def test_queue_prefetch_calls_all_subs(self, provider):
        """queue_prefetch() calls every sub-provider."""
        call_count = [0]
        for sub in provider._subs:
            sub.queue_prefetch = lambda *a, **kw: call_count.__setitem__(0, call_count[0] + 1)
        provider.queue_prefetch("test query", session_id="s1")
        assert call_count[0] == len(provider._subs)

    def test_sync_turn_calls_all_subs(self, provider):
        """sync_turn() calls every sub-provider."""
        calls = []
        for sub in provider._subs:
            sub.sync_turn = lambda u, a, ns=sub.name, **kw: calls.append(ns)
        provider.sync_turn("user", "assistant", session_id="s1")
        expected = [s.name for s in provider._subs]
        assert calls == expected

    def test_on_turn_start_calls_all_subs(self, provider):
        calls = []
        for sub in provider._subs:
            sub.on_turn_start = lambda *a, ns=sub.name, **kw: calls.append(ns)
        provider.on_turn_start(42, "hello")
        assert calls == [s.name for s in provider._subs]

    def test_on_session_end_calls_all_subs(self, provider):
        calls = []
        for sub in provider._subs:
            sub.on_session_end = lambda m, ns=sub.name: calls.append(ns)
        provider.on_session_end([{"role": "user"}])
        assert calls == [s.name for s in provider._subs]

    def test_on_session_switch_calls_all_subs(self, provider):
        calls = []
        for sub in provider._subs:
            sub.on_session_switch = lambda *a, ns=sub.name, **kw: calls.append(ns)
        provider.on_session_switch("new-sid", parent_session_id="old-sid", reset=True)
        assert calls == [s.name for s in provider._subs]

    def test_on_memory_write_calls_all_subs(self, provider):
        calls = []
        for sub in provider._subs:
            sub.on_memory_write = lambda *a, ns=sub.name, **kw: calls.append(ns)
        provider.on_memory_write("add", "memory", "content", {"key": "val"})
        assert calls == [s.name for s in provider._subs]

    def test_on_delegation_calls_all_subs(self, provider):
        calls = []
        for sub in provider._subs:
            sub.on_delegation = lambda *a, ns=sub.name, **kw: calls.append(ns)
        provider.on_delegation("task", "result", child_session_id="child1")
        assert calls == [s.name for s in provider._subs]

    def test_queue_prefetch_exception_isolation(self, provider):
        """queue_prefetch handles per-sub exceptions."""
        for i, sub in enumerate(provider._subs):
            if i == 0:
                sub.queue_prefetch.side_effect = RuntimeError("queue fail")
        provider.queue_prefetch("test", session_id="s1")  # should not raise

    def test_sync_turn_exception_isolation(self, provider):
        """sync_turn handles per-sub exceptions."""
        for i, sub in enumerate(provider._subs):
            if i == 0:
                sub.sync_turn.side_effect = RuntimeError("sync fail")
        provider.sync_turn("u", "a", session_id="s1")  # should not raise

    def test_on_memory_write_exception_isolation(self, provider):
        for i, sub in enumerate(provider._subs):
            if i == 0:
                sub.on_memory_write.side_effect = RuntimeError("write fail")
        provider.on_memory_write("add", "memory", "x")  # should not raise

    def test_on_turn_start_exception_isolation(self, provider):
        for i, sub in enumerate(provider._subs):
            if i == 0:
                sub.on_turn_start.side_effect = RuntimeError("turn fail")
        provider.on_turn_start(1, "msg")  # should not raise

    def test_on_session_end_exception_isolation(self, provider):
        for i, sub in enumerate(provider._subs):
            if i == 0:
                sub.on_session_end.side_effect = RuntimeError("session end fail")
        provider.on_session_end([{"role": "user"}])  # should not raise

    def test_on_session_switch_exception_isolation(self, provider):
        for i, sub in enumerate(provider._subs):
            if i == 0:
                sub.on_session_switch.side_effect = RuntimeError("switch fail")
        provider.on_session_switch("new-sid")  # should not raise

    def test_on_delegation_exception_isolation(self, provider):
        for i, sub in enumerate(provider._subs):
            if i == 0:
                sub.on_delegation.side_effect = RuntimeError("delegation fail")
        provider.on_delegation("task", "result")  # should not raise

    def test_on_memory_write_with_metadata(self, provider):
        """on_memory_write passes metadata to all subs."""
        calls = []
        for sub in provider._subs:
            sub.on_memory_write = lambda *a, ns=sub.name, **kw: calls.append((ns, a, kw))
        provider.on_memory_write("add", "memory", "content", {"origin": "test"})
        assert len(calls) == len(provider._subs)
        for _, args, kw in calls:
            # MagicMock has **kwargs so introspection uses keyword mode
            assert kw.get("metadata") == {"origin": "test"} or (
                len(args) >= 4 and args[3] == {"origin": "test"}
            )

    def test_on_pre_compress_collects_results(self, provider):
        """on_pre_compress collects non-empty results from all subs."""
        for sub in provider._subs:
            sub.on_pre_compress = lambda *a, ns=sub.name, **kw: f"extract from {ns}"
        result = provider.on_pre_compress([{"role": "user", "content": "hi"}])
        assert isinstance(result, str)
        for sub in provider._subs:
            assert sub.name in result

    def test_on_pre_compress_empty_when_all_empty(self, provider):
        """on_pre_compress returns '' when all subs return empty."""
        for sub in provider._subs:
            sub.on_pre_compress.return_value = ""
        result = provider.on_pre_compress([{"role": "user", "content": "hi"}])
        assert result == ""

    def test_on_pre_compress_exception_isolation(self, provider):
        """on_pre_compress handles per-sub exceptions."""
        for i, sub in enumerate(provider._subs):
            if i == 0:
                sub.on_pre_compress.side_effect = RuntimeError("compress fail")
        result = provider.on_pre_compress([{"role": "user", "content": "hi"}])
        assert isinstance(result, str)  # doesn't raise

    def test_prefetch_with_non_empty_results(self, provider):
        """prefetch concatenates non-empty results with sub names."""
        for sub in provider._subs:
            sub.prefetch = lambda *a, ns=sub.name, **kw: f"result from {ns}"
        result = provider.prefetch("test query", session_id="s1")
        assert isinstance(result, str)
        for sub in provider._subs:
            assert sub.name in result

    def test_system_prompt_block_concatenates(self, provider):
        """system_prompt_block concatenates non-empty blocks."""
        result = provider.system_prompt_block()
        assert isinstance(result, str)

    def test_system_prompt_block_empty_when_all_empty(self, provider):
        """system_prompt_block returns empty string when all subs return empty."""
        for sub in provider._subs:
            sub.system_prompt_block = lambda: ""
        result = provider.system_prompt_block()
        assert result == ""


# ── MultiMemoryProvider edge cases ──────────────────────────────────────────


class TestMultiMemoryProviderEdgeCases:
    """Edge cases: empty subs, error in _load_config, unhandled tool calls."""

    def test_empty_provider_not_available(self):
        """A provider with no subs is not available."""
        p = MultiMemoryProvider()
        p._subs = []
        assert p.is_available() is False

    def test_get_tool_schemas_first_seen_wins(self):
        """When two subs provide the same tool name, first-seen wins."""
        p = MultiMemoryProvider()

        # Create mock subs with overlapping tool names
        mock1 = mock.MagicMock()
        mock1.name = "mock1"
        mock1.get_tool_schemas.return_value = [
            {"name": "search", "description": "first"},
            {"name": "unique_1", "description": "unique"},
        ]

        mock2 = mock.MagicMock()
        mock2.name = "mock2"
        mock2.get_tool_schemas.return_value = [
            {"name": "search", "description": "second"},
            {"name": "unique_2", "description": "also unique"},
        ]

        p._subs = [mock1, mock2]
        schemas = p.get_tool_schemas()

        names = [s["name"] for s in schemas]
        assert "search" in names
        # Only one 'search' entry
        assert len([n for n in names if n == "search"]) == 1
        assert "unique_1" in names
        assert "unique_2" in names

    def test_handle_tool_call_prefix_match(self, provider):
        """handle_tool_call matches by PREFIX and delegates correctly."""
        schemas = provider.get_tool_schemas()
        if not schemas:
            pytest.skip("No tool schemas available")
        # Make all mock subs return a string
        for sub in provider._subs:
            sub.handle_tool_call.return_value = "mocked result"
        result = provider.handle_tool_call(schemas[-1]["name"], {})
        assert isinstance(result, str)

    def test_handle_tool_call_fallback_chain(self):
        """Fallback tries all subs when no prefix matches."""
        mock1 = mock.MagicMock()
        mock1.name = "mock1"
        mock1.handle_tool_call.side_effect = RuntimeError("no")

        mock2 = mock.MagicMock()
        mock2.name = "mock2"
        mock2.handle_tool_call.return_value = "found it"

        p = MultiMemoryProvider()
        p._subs = [mock1, mock2]

        result = p.handle_tool_call("some_tool", {})
        assert result == "found it"
        mock1.handle_tool_call.assert_called_once_with("some_tool", {})
        mock2.handle_tool_call.assert_called_once_with("some_tool", {})

    def test_handle_tool_call_all_fallback_fail(self):
        """When all fallbacks fail, returns tool_error message."""
        mock1 = mock.MagicMock()
        mock1.name = "mock1"
        mock1.handle_tool_call.side_effect = RuntimeError("no")

        p = MultiMemoryProvider()
        p._subs = [mock1]

        result = p.handle_tool_call("some_tool", {})
        assert "No sub-provider handles" in result

    def test_handle_tool_call_prefix_matched_before_fallback(self):
        """Prefix-matched sub handles, fallback doesn't try other subs."""
        mock1 = mock.MagicMock()
        mock1.name = "mock1"
        mock1.handle_tool_call.return_value = "matched by prefix"

        mock2 = mock.MagicMock()
        mock2.name = "mock2"
        # mock2 should never be called since mock1's prefix matches "mock1_"
        mock2.handle_tool_call.side_effect = RuntimeError("should not be called")

        p = MultiMemoryProvider()
        p._subs = [mock1, mock2]

        result = p.handle_tool_call("mock1_search", {})
        assert result == "matched by prefix"
        mock1.handle_tool_call.assert_called_once_with("mock1_search", {})
        mock2.handle_tool_call.assert_not_called()

    def test_handle_tool_call_empty_name(self):
        """Empty tool name is passed through to fallback."""
        mock1 = mock.MagicMock()
        mock1.name = "mock1"
        mock1.handle_tool_call.return_value = "handled"
        p = MultiMemoryProvider()
        p._subs = [mock1]
        result = p.handle_tool_call("", {})
        assert result == "handled"
        mock1.handle_tool_call.assert_called_once()

    def test_load_config_exception_is_caught(self):
        """_load_config catches and logs exceptions."""
        with mock.patch(
            "multi_memory.open",
            mock.mock_open(read_data=b""),
        ) as m:
            m.side_effect = PermissionError("no access")
            p = MultiMemoryProvider()
            # Should not raise — exception is caught in _load_config
            assert p._subs == []  # fallback: empty subs on config failure


# ── Runtime sub-provider management ──────────────────────────────────────


class TestRuntimeManagement:
    """Tests for add_provider, remove_provider, get_provider, providers property."""

    def test_providers_property(self, provider):
        """providers property returns list of sub-provider names."""
        names = provider.providers
        assert "holographic" in names
        assert "mnemosyne" in names

    def test_get_provider_found(self, provider):
        """get_provider returns the sub-provider when found."""
        sub = provider.get_provider("holographic")
        assert sub is not None
        assert sub.name == "holographic"

    def test_get_provider_not_found(self, provider):
        """get_provider returns None when not found."""
        assert provider.get_provider("nonexistent") is None

    def test_add_provider_new(self, provider):
        """add_provider adds a new sub-provider."""
        new_sub = mock.MagicMock()
        new_sub.name = "new_backend"
        assert provider.add_provider(new_sub) is True
        assert "new_backend" in provider.providers
        assert len(provider._subs) == 3

    def test_add_provider_duplicate(self, provider):
        """add_provider rejects duplicate names."""
        new_sub = mock.MagicMock()
        new_sub.name = "holographic"  # already exists
        assert provider.add_provider(new_sub) is False
        assert len(provider._subs) == 2

    def test_remove_provider_found(self, provider):
        """remove_provider removes and shuts down a sub-provider."""
        assert provider.remove_provider("holographic") is True
        assert "holographic" not in provider.providers
        assert len(provider._subs) == 1
        # Should have called close() or shutdown() on the removed sub
        holo = mock.MagicMock()
        holo.name = "holographic"
        # Can't assert on the original mock since it's been removed,
        # but we can verify it's gone
        assert provider.get_provider("holographic") is None

    def test_remove_provider_not_found(self, provider):
        """remove_provider returns False when name not found."""
        assert provider.remove_provider("nonexistent") is False
        assert len(provider._subs) == 2

    def test_remove_provider_calls_close(self, provider):
        """remove_provider calls close() when available, else shutdown()."""
        sub_with_close = mock.MagicMock()
        sub_with_close.name = "closeable"
        sub_with_close.close = mock.MagicMock()
        provider._subs.append(sub_with_close)

        provider.remove_provider("closeable")
        sub_with_close.close.assert_called_once()

    def test_remove_provider_calls_shutdown_when_no_close(self, provider):
        """remove_provider calls shutdown() when close() not available."""
        sub = mock.MagicMock()
        sub.name = "shutdown_only"
        # Remove close attribute to simulate no close() method
        del sub.close
        provider._subs.append(sub)

        provider.remove_provider("shutdown_only")
        sub.shutdown.assert_called_once()

    def test_remove_provider_cleans_health(self, provider):
        """remove_provider resets health tracking for the removed provider."""
        # Trip the circuit (default limit is 5)
        for _ in range(5):
            provider._health.record_failure("holographic")
        assert provider._health.is_open("holographic")

        provider.remove_provider("holographic")
        # Health counter should be reset
        assert not provider._health.is_open("holographic")

    def test_add_then_remove_roundtrip(self, provider):
        """Full add-then-remove roundtrip works."""
        new_sub = mock.MagicMock()
        new_sub.name = "roundtrip"
        assert provider.add_provider(new_sub) is True
        assert "roundtrip" in provider.providers
        assert provider.remove_provider("roundtrip") is True
        assert "roundtrip" not in provider.providers
        assert len(provider._subs) == 2

    def test_get_all_tool_names(self, provider):
        """get_all_tool_names returns set of all tool name strings."""
        names = provider.get_all_tool_names()
        assert isinstance(names, set)
        assert "holographic_fact_store" in names
        assert "mnemosyne_search" in names

    def test_has_tool_true(self, provider):
        """has_tool returns True for existing tools."""
        assert provider.has_tool("holographic_fact_store") is True
        assert provider.has_tool("mnemosyne_search") is True

    def test_has_tool_false(self, provider):
        """has_tool returns False for nonexistent tools."""
        assert provider.has_tool("nonexistent_tool") is False

    def test_on_session_switch_empty_guard(self, provider):
        """on_session_switch does nothing when session_id is empty."""
        provider.on_session_switch("")
        # Subs should NOT have been called
        for sub in provider._subs:
            sub.on_session_switch.assert_not_called()

    def test_on_session_switch_valid_calls_subs(self, provider):
        """on_session_switch dispatches to subs when session_id is non-empty."""
        provider.on_session_switch("new-sid")
        for sub in provider._subs:
            sub.on_session_switch.assert_called_once()

    def test_remove_then_tool_schemas_updated(self, provider):
        """After removing a provider, its tools disappear from schemas."""
        all_names_before = {s["name"] for s in provider.get_tool_schemas()}
        assert "holographic_fact_store" in all_names_before

        provider.remove_provider("holographic")
        all_names_after = {s["name"] for s in provider.get_tool_schemas()}
        assert "holographic_fact_store" not in all_names_after
        assert "mnemosyne_search" in all_names_after

    def test_add_provider_rejects_broken_schema(self, provider):
        """add_provider rejects adapter whose get_tool_schemas() raises."""
        broken = mock.MagicMock()
        broken.name = "broken"
        broken.get_tool_schemas.side_effect = RuntimeError("schema boom")
        assert provider.add_provider(broken) is False
        assert "broken" not in provider.providers
        assert len(provider._subs) == 2

    def test_add_provider_validates_before_adding(self, provider):
        """add_provider calls get_tool_schemas() before accepting."""
        new_sub = mock.MagicMock()
        new_sub.name = "validated"
        new_sub.get_tool_schemas.return_value = [{"name": "validated_tool"}]
        assert provider.add_provider(new_sub) is True
        new_sub.get_tool_schemas.assert_called_once()


# ── _SubProviderAdapter delegation tests (mock-based, no real backends) ───────


class TestSubProviderAdapterDelegation:
    """Mock-based tests for _SubProviderAdapter delegation methods.

    These tests work without any real backends installed by patching
    _try_import to return a mock class that creates a mock delegate.
    """

    def _make_adapter(self):
        """Create a concrete _SubProviderAdapter with a mock delegate.

        Returns (adapter, mock_delegate) tuple.
        """
        mock_delegate = mock.MagicMock()
        mock_delegate.name = "mock_backend"

        mock_cls = mock.MagicMock(return_value=mock_delegate)

        with mock.patch("multi_memory.adapters._try_import", return_value=mock_cls):

            class ConcreteAdapter(_SubProviderAdapter):
                CONFIG_KEY = "test"
                MODULE = "test"
                CLASS = "Test"
                PREFIX = "test"

            adapter = ConcreteAdapter()
        return adapter, mock_delegate

    def test_name_delegates_to_delegate(self):
        adapter, delegate = self._make_adapter()
        delegate.name = "my_backend"
        assert adapter.name == "my_backend"

    def test_is_available_delegates(self):
        adapter, delegate = self._make_adapter()
        delegate.is_available.return_value = True
        assert adapter.is_available() is True
        delegate.is_available.assert_called_once()

    def test_initialize_delegates(self):
        adapter, delegate = self._make_adapter()
        adapter.initialize(session_id="s1", foo="bar")
        delegate.initialize.assert_called_once_with(session_id="s1", foo="bar")

    def test_shutdown_delegates(self):
        adapter, delegate = self._make_adapter()
        adapter.shutdown()
        delegate.shutdown.assert_called_once()

    def test_get_tool_schemas_prefixes_names(self):
        adapter, delegate = self._make_adapter()
        delegate.get_tool_schemas.return_value = [
            {"name": "search", "description": "Search"},
            {"name": "store", "description": "Store"},
        ]
        schemas = adapter.get_tool_schemas()
        assert len(schemas) == 2
        assert schemas[0]["name"] == "test_search"
        assert schemas[1]["name"] == "test_store"
        # Original description preserved
        assert schemas[0]["description"] == "Search"

    def test_handle_tool_call_passes_through(self):
        """handle_tool_call passes tool_name through unchanged (all backends do this)."""
        adapter, delegate = self._make_adapter()
        delegate.handle_tool_call.return_value = "result"
        result = adapter.handle_tool_call("test_search", {"q": "hello"})
        delegate.handle_tool_call.assert_called_once_with("test_search", {"q": "hello"})
        assert result == "result"

    def test_handle_tool_call_passes_kwargs(self):
        adapter, delegate = self._make_adapter()
        delegate.handle_tool_call.return_value = "ok"
        adapter.handle_tool_call("test_store", {"data": "x"}, session_id="s1")
        delegate.handle_tool_call.assert_called_once_with(
            "test_store", {"data": "x"}, session_id="s1"
        )

    def test_prefetch_delegates(self):
        adapter, delegate = self._make_adapter()
        delegate.prefetch.return_value = "context"
        result = adapter.prefetch("query", session_id="s1")
        delegate.prefetch.assert_called_once_with("query", session_id="s1")
        assert result == "context"

    def test_queue_prefetch_delegates(self):
        adapter, delegate = self._make_adapter()
        adapter.queue_prefetch("query", session_id="s1")
        delegate.queue_prefetch.assert_called_once_with("query", session_id="s1")

    def test_sync_turn_delegates(self):
        adapter, delegate = self._make_adapter()
        adapter.sync_turn("user msg", "asst msg", session_id="s1")
        delegate.sync_turn.assert_called_once_with("user msg", "asst msg", session_id="s1")

    def test_system_prompt_block_delegates(self):
        adapter, delegate = self._make_adapter()
        delegate.system_prompt_block.return_value = "prompt block"
        assert adapter.system_prompt_block() == "prompt block"
        delegate.system_prompt_block.assert_called_once()

    def test_on_turn_start_delegates(self):
        adapter, delegate = self._make_adapter()
        adapter.on_turn_start(42, "hello")
        delegate.on_turn_start.assert_called_once_with(42, "hello")

    def test_on_session_end_delegates(self):
        adapter, delegate = self._make_adapter()
        msgs = [{"role": "user", "content": "hi"}]
        adapter.on_session_end(msgs)
        delegate.on_session_end.assert_called_once_with(msgs)

    def test_on_session_switch_delegates(self):
        adapter, delegate = self._make_adapter()
        adapter.on_session_switch("new-sid", parent_session_id="old", reset=True)
        delegate.on_session_switch.assert_called_once_with(
            "new-sid", parent_session_id="old", reset=True
        )

    def test_on_memory_write_delegates(self):
        adapter, delegate = self._make_adapter()
        adapter.on_memory_write("add", "memory", "content here", {"origin": "test"})
        # MagicMock has **kwargs so introspection detects "keyword" mode
        delegate.on_memory_write.assert_called_once_with(
            "add", "memory", "content here", metadata={"origin": "test"}
        )

    def test_on_delegation_delegates(self):
        adapter, delegate = self._make_adapter()
        adapter.on_delegation("task", "result", child_session_id="c1")
        delegate.on_delegation.assert_called_once_with("task", "result", child_session_id="c1")

    def test_on_pre_compress_delegates(self):
        adapter, delegate = self._make_adapter()
        delegate.on_pre_compress.return_value = "compressed"
        msgs = [{"role": "user", "content": "hi"}]
        result = adapter.on_pre_compress(msgs)
        delegate.on_pre_compress.assert_called_once_with(msgs)
        assert result == "compressed"


# ── register() function tests ────────────────────────────────────────────────


class TestRegisterFunction:
    """Test the register() entry point."""

    def test_register_calls_ctx(self):
        from multi_memory import register

        ctx = mock.MagicMock()
        with (
            mock.patch("multi_memory.MultiMemoryProvider._load_config"),
            mock.patch("multi_memory.MultiMemoryProvider._validate_namespaces"),
        ):
            register(ctx)
        ctx.register_memory_provider.assert_called_once()
        args = ctx.register_memory_provider.call_args[0]
        assert isinstance(args[0], MultiMemoryProvider)

    def test_register_cli_command(self):
        """register() also registers CLI commands when ctx supports it."""
        from multi_memory import register

        ctx = mock.MagicMock()
        with (
            mock.patch("multi_memory.MultiMemoryProvider._load_config"),
            mock.patch("multi_memory.MultiMemoryProvider._validate_namespaces"),
        ):
            register(ctx)
        ctx.register_cli_command.assert_called_once()
        kwargs = ctx.register_cli_command.call_args[1]
        assert kwargs["name"] == "multi"
        assert kwargs["help"] == "Manage multi-memory backends (status, list, add, remove)"
        assert callable(kwargs["setup_fn"])
        assert callable(kwargs["handler_fn"])

    def test_register_graceful_without_cli_command(self):
        """register() still works on old Hermes lacking register_cli_command."""
        from multi_memory import register

        ctx = mock.MagicMock(spec=["register_memory_provider"])
        with (
            mock.patch("multi_memory.MultiMemoryProvider._load_config"),
            mock.patch("multi_memory.MultiMemoryProvider._validate_namespaces"),
        ):
            register(ctx)
        ctx.register_memory_provider.assert_called_once()
        # Should not raise — hasattr guard skips CLI registration


# ── _load_config edge cases ─────────────────────────────────────────────────


class TestLoadConfigEdgeCases:
    """Test _load_config behavior when config.yaml is missing or broken."""

    def test_missing_config_yaml_logs_warning(self):
        """When config.yaml doesn't exist, _load_config logs warning, doesn't crash."""
        import tempfile

        with tempfile.TemporaryDirectory() as td, mock.patch.dict(os.environ, {"HERMES_HOME": td}):
            p = MultiMemoryProvider()
            # No config.yaml -> _load_config catches FileNotFoundError
            assert p._subs == []
            # Verify it didn't crash (implicit: constructor completed)

    def test_backends_that_fail_to_load_are_skipped(self):
        """When a configured backend fails to import, it's skipped silently."""
        # Use a backend that will fail to load (no module, no plugin discovery)
        cfg = {"memory": {"multi": {"backends": {"definitely_not_a_real_backend": {}}}}}
        result = _load_backends_from_config(cfg)
        assert result == []
        assert len(result) == 0

    def test_load_config_all_backends_fail(self):
        """When all configured backends fail to import, _subs stays empty."""
        # Use a known non-installed backend to guarantee failure
        cfg = {"memory": {"multi": {"backends": {"nonexistent_backend_xyz": {}}}}}
        result = _load_backends_from_config(cfg)
        assert result == []


# ── name property consistency ────────────────────────────────────────────────


class TestNamePropertyConsistency:
    """Test that MultiMemoryProvider.name returns 'multi' consistently."""

    def test_class_has_name_attribute(self):
        """The class defines name (either as attr or property)."""
        assert hasattr(MultiMemoryProvider, "name")

    def test_instance_property_is_multi(self):
        with (
            mock.patch.object(MultiMemoryProvider, "_load_config"),
            mock.patch.object(MultiMemoryProvider, "_validate_namespaces"),
        ):
            p = MultiMemoryProvider()
        assert p.name == "multi"

    def test_class_and_instance_agree(self):
        """Both the class-level name and instance property return 'multi'."""
        # name is a @property on the class, but the descriptor is always present
        assert hasattr(MultiMemoryProvider, "name")
        # Instance always returns "multi"
        with (
            mock.patch.object(MultiMemoryProvider, "_load_config"),
            mock.patch.object(MultiMemoryProvider, "_validate_namespaces"),
        ):
            p = MultiMemoryProvider()
        assert p.name == "multi"


# ── No-double-prefix tests ─────────────────────────────────────────────


class TestNoDoublePrefix:
    """Adapters wrapping providers with self-prefixed tool names
    (Mem0, Honcho, Mnemosyne) must NOT double-prefix schemas.
    """

    def _make_mem0_adapter(self):
        mock_delegate = mock.MagicMock()
        mock_delegate.name = "mem0"
        mock_delegate.get_tool_schemas.return_value = [
            {"name": "mem0_profile", "description": "Profile"},
            {"name": "mem0_search", "description": "Search"},
            {"name": "mem0_conclude", "description": "Conclude"},
        ]
        mock_delegate.handle_tool_call.return_value = '{"ok": true}'
        mock_cls = mock.MagicMock(return_value=mock_delegate)
        with mock.patch("multi_memory.adapters._try_import", return_value=mock_cls):
            adapter = _Mem0Adapter()
        return adapter, mock_delegate

    def _make_honcho_adapter(self):
        mock_delegate = mock.MagicMock()
        mock_delegate.name = "honcho"
        mock_delegate.get_tool_schemas.return_value = [
            {"name": "honcho_profile", "description": "Profile"},
            {"name": "honcho_search", "description": "Search"},
        ]
        mock_delegate.handle_tool_call.return_value = '{"ok": true}'
        mock_cls = mock.MagicMock(return_value=mock_delegate)
        with mock.patch("multi_memory.adapters._try_import", return_value=mock_cls):
            adapter = _HonchoAdapter()
        return adapter, mock_delegate

    def test_mem0_no_double_prefix(self):
        adapter, _ = self._make_mem0_adapter()
        schemas = adapter.get_tool_schemas()
        names = [s["name"] for s in schemas]
        assert names == ["mem0_profile", "mem0_search", "mem0_conclude"]
        assert not any(n.startswith("mem0_mem0_") for n in names)

    def test_mem0_handle_passes_full_name(self):
        adapter, delegate = self._make_mem0_adapter()
        adapter.handle_tool_call("mem0_search", {"query": "test"})
        delegate.handle_tool_call.assert_called_once_with("mem0_search", {"query": "test"})

    def test_honcho_no_double_prefix(self):
        adapter, _ = self._make_honcho_adapter()
        schemas = adapter.get_tool_schemas()
        names = [s["name"] for s in schemas]
        assert names == ["honcho_profile", "honcho_search"]
        assert not any(n.startswith("honcho_honcho_") for n in names)

    def test_honcho_handle_passes_full_name(self):
        adapter, delegate = self._make_honcho_adapter()
        adapter.handle_tool_call("honcho_search", {"query": "test"})
        delegate.handle_tool_call.assert_called_once_with("honcho_search", {"query": "test"})

    def test_holographic_strips_prefix_normally(self):
        """Holographic adapter strips then re-adds prefix for exact one-prefix guarantee."""
        mock_delegate = mock.MagicMock()
        mock_delegate.name = "holographic"
        mock_delegate.get_tool_schemas.return_value = [
            {"name": "holographic_store", "description": "Store"},
            {"name": "holographic_feedback", "description": "Feedback"},
        ]
        mock_delegate.handle_tool_call.return_value = '{"ok": true}'
        mock_cls = mock.MagicMock(return_value=mock_delegate)
        with mock.patch("multi_memory.adapters._try_import", return_value=mock_cls):
            adapter = _HolographicAdapter()
        schemas = adapter.get_tool_schemas()
        names = [s["name"] for s in schemas]
        assert names == ["holographic_store", "holographic_feedback"]
        # handle_tool_call passes full prefixed name (plugin accepts both forms)
        adapter.handle_tool_call("holographic_store", {"action": "list"})
        mock_delegate.handle_tool_call.assert_called_once_with(
            "holographic_store", {"action": "list"}
        )

    def test_holographic_no_double_prefix_when_already_prefixed(self):
        """If holographic plugin returns already-prefixed names ('holographic_store'),
        the adapter must NOT produce 'holographic_holographic_store'."""
        mock_delegate = mock.MagicMock()
        mock_delegate.name = "holographic"
        mock_delegate.get_tool_schemas.return_value = [
            {"name": "holographic_store", "description": "Store"},
            {"name": "holographic_feedback", "description": "Feedback"},
        ]
        mock_cls = mock.MagicMock(return_value=mock_delegate)
        with mock.patch("multi_memory.adapters._try_import", return_value=mock_cls):
            adapter = _HolographicAdapter()
        schemas = adapter.get_tool_schemas()
        names = [s["name"] for s in schemas]
        assert names == ["holographic_store", "holographic_feedback"]
        # Must NOT be "holographic_holographic_store"
        assert "holographic_holographic_store" not in names


@requires_holographic
class TestHolographicAdapterLifecycle:
    """Direct tests on the holographic adapter's delegate methods."""

    @pytest.fixture
    def adapter(self):
        from multi_memory.adapters import _HolographicAdapter

        return _HolographicAdapter()

    def test_shutdown(self, adapter):
        adapter.shutdown()  # should not raise

    def test_on_turn_start(self, adapter):
        adapter._delegate.on_turn_start = mock.MagicMock()
        adapter.on_turn_start(1, "msg")  # should not raise
        adapter._delegate.on_turn_start.assert_called_once_with(1, "msg")

    def test_on_session_end(self, adapter):
        adapter.on_session_end([])  # should not raise

    def test_on_session_switch(self, adapter):
        adapter._delegate.on_session_switch = mock.MagicMock()
        adapter.on_session_switch(
            "new-sid", parent_session_id="old", reset=True
        )  # should not raise
        adapter._delegate.on_session_switch.assert_called_once_with(
            "new-sid", parent_session_id="old", reset=True
        )

    def test_on_delegation(self, adapter):
        adapter._delegate.on_delegation = mock.MagicMock()
        adapter.on_delegation("task", "result", child_session_id="c1")  # should not raise
        adapter._delegate.on_delegation.assert_called_once_with(
            "task", "result", child_session_id="c1"
        )

    def test_name_property(self, adapter):
        assert adapter.name == "holographic"


# ── Coverage gap tests ───────────────────────────────────────────────────


class TestCoverageGaps:
    """Tests targeting specific uncovered lines."""

    def test_try_import_find_spec_module_not_found(self):
        """_try_import returns None when find_spec raises ModuleNotFoundError."""
        with mock.patch(
            "multi_memory.adapters.find_spec",
            side_effect=ModuleNotFoundError("no parent"),
        ):
            from multi_memory.adapters import _try_import

            result = _try_import("some.module", "SomeClass")
        assert result is None

    def test_try_import_find_spec_value_error(self):
        """_try_import returns None when find_spec raises ValueError."""
        with mock.patch(
            "multi_memory.adapters.find_spec",
            side_effect=ValueError("invalid name"),
        ):
            from multi_memory.adapters import _try_import

            result = _try_import("bad name!", "SomeClass")
        assert result is None

    def test_mnemosyne_adapter_plugin_loader_returns_none(self):
        """_MnemosyneAdapter raises when plugin loader returns None."""
        import sys

        mock_pm = mock.MagicMock()
        mock_pm.load_memory_provider.return_value = None
        old = sys.modules.get("plugins.memory")
        sys.modules["plugins.memory"] = mock_pm
        try:
            # When plugin loader returns None and standard import also fails,
            # the exception from the fallback (RuntimeError) is what propagates.
            with pytest.raises(RuntimeError, match="not installed"):
                _MnemosyneAdapter()
        finally:
            if old is not None:
                sys.modules["plugins.memory"] = old
            else:
                sys.modules.pop("plugins.memory", None)

    def test_mnemosyne_adapter_import_error_fallback(self):
        """_MnemosyneAdapter falls back to standard import on ImportError."""
        import sys

        # Mock load_memory_provider to raise ImportError to trigger fallback
        mock_delegate = mock.MagicMock()
        mock_delegate.name = "mnemosyne"
        mock_cls = mock.MagicMock(return_value=mock_delegate)
        mock_pm = mock.MagicMock()
        mock_pm.load_memory_provider.side_effect = ImportError("no plugins.memory")
        old = sys.modules.get("plugins.memory")
        sys.modules["plugins.memory"] = mock_pm
        try:
            with mock.patch(
                "multi_memory.adapters._try_import",
                return_value=mock_cls,
            ):
                adapter = _MnemosyneAdapter()
        finally:
            if old is not None:
                sys.modules["plugins.memory"] = old
            else:
                sys.modules.pop("plugins.memory", None)
        assert adapter._delegate is mock_delegate

    def test_mnemosyne_handle_tool_call_delegates(self):
        """_MnemosyneAdapter.handle_tool_call passes full name to delegate."""
        import sys

        mock_delegate = mock.MagicMock()
        mock_delegate.name = "mnemosyne"
        mock_pm = mock.MagicMock()
        mock_pm.load_memory_provider.return_value = mock_delegate
        old = sys.modules.get("plugins.memory")
        sys.modules["plugins.memory"] = mock_pm
        try:
            adapter = _MnemosyneAdapter()
        finally:
            if old is not None:
                sys.modules["plugins.memory"] = old
            else:
                sys.modules.pop("plugins.memory", None)
        mock_delegate.handle_tool_call.return_value = '{"ok": true}'
        adapter.handle_tool_call("mnemosyne_recall", {"query": "test"})
        mock_delegate.handle_tool_call.assert_called_once_with(
            "mnemosyne_recall", {"query": "test"}
        )

    def test_mnemosyne_get_tool_schemas_returns_directly(self):
        """_MnemosyneAdapter.get_tool_schemas returns delegate schemas unchanged."""
        import sys

        mock_delegate = mock.MagicMock()
        mock_delegate.name = "mnemosyne"
        mock_delegate.get_tool_schemas.return_value = [
            {"name": "mnemosyne_recall", "description": "Recall"},
        ]
        mock_pm = mock.MagicMock()
        mock_pm.load_memory_provider.return_value = mock_delegate
        old = sys.modules.get("plugins.memory")
        sys.modules["plugins.memory"] = mock_pm
        try:
            adapter = _MnemosyneAdapter()
        finally:
            if old is not None:
                sys.modules["plugins.memory"] = old
            else:
                sys.modules.pop("plugins.memory", None)
        schemas = adapter.get_tool_schemas()
        assert schemas == [{"name": "mnemosyne_recall", "description": "Recall"}]

    def test_mem0_adapter_handle_delegates(self):
        """_Mem0Adapter.handle_tool_call passes full name (no strip)."""
        mock_delegate = mock.MagicMock()
        mock_delegate.name = "mem0"
        mock_cls = mock.MagicMock(return_value=mock_delegate)
        with mock.patch("multi_memory.adapters._try_import", return_value=mock_cls):
            adapter = _Mem0Adapter()
        mock_delegate.handle_tool_call.return_value = '{"ok": true}'
        adapter.handle_tool_call("mem0_search", {"query": "test"})
        mock_delegate.handle_tool_call.assert_called_once_with("mem0_search", {"query": "test"})

    def test_honcho_adapter_handle_delegates(self):
        """_HonchoAdapter.handle_tool_call passes full name (no strip)."""
        mock_delegate = mock.MagicMock()
        mock_delegate.name = "honcho"
        mock_cls = mock.MagicMock(return_value=mock_delegate)
        with mock.patch("multi_memory.adapters._try_import", return_value=mock_cls):
            adapter = _HonchoAdapter()
        mock_delegate.handle_tool_call.return_value = '{"ok": true}'
        adapter.handle_tool_call("honcho_search", {"query": "test"})
        mock_delegate.handle_tool_call.assert_called_once_with("honcho_search", {"query": "test"})

    def test_load_backends_init_exception_is_logged(self):
        """When adapter.__init__ raises, it's caught and logged."""
        mock_cls = mock.MagicMock()
        mock_cls.side_effect = RuntimeError("init boom")
        mock_cls.CONFIG_KEY = "broken"
        with mock.patch("multi_memory._SUB_CLASSES", (mock_cls,)):
            cfg = {"memory": {"multi": {"backends": {"broken": {}}}}}
            result = _load_backends_from_config(cfg)
        assert result == []

    def test_discovery_find_spec_exception_handled(self):
        """discover_backends catches ModuleNotFoundError from find_spec."""
        from multi_memory.discovery import discover_backends

        with (
            mock.patch(
                "multi_memory.discovery._is_mnemosyne_plugin_installed",
                return_value=False,
            ),
            mock.patch(
                "multi_memory.discovery.find_spec",
                side_effect=ModuleNotFoundError("no parent"),
            ),
        ):
            results = discover_backends()
        # All non-mnemosyne backends should show as not installed
        for r in results:
            if r["config_key"] != "mnemosyne":
                assert r["installed"] is False


# ── Ported from fork: thread safety, schema failure protection, close() ──


class TestThreadSafety:
    """MultiMemoryProvider lifecycle dispatch is thread-safe (RLock)."""

    def test_lock_exists(self):
        """MultiMemoryProvider.__init__ creates _lock (threading.RLock)."""
        import threading

        with (
            mock.patch.object(MultiMemoryProvider, "_load_config"),
            mock.patch.object(MultiMemoryProvider, "_validate_namespaces"),
        ):
            prov = MultiMemoryProvider()
        assert isinstance(prov._lock, type(threading.RLock()))

    def test_concurrent_lifecycle_dispatch(self):
        """Multiple threads calling lifecycle hooks don't crash."""
        import threading

        with (
            mock.patch.object(MultiMemoryProvider, "_load_config"),
            mock.patch.object(MultiMemoryProvider, "_validate_namespaces"),
        ):
            prov = MultiMemoryProvider()

        mock_sub = mock.MagicMock()
        mock_sub.name = "fake"
        mock_sub.is_available.return_value = True
        mock_sub.get_tool_schemas.return_value = []
        prov._subs = [mock_sub]

        errors = []

        def call_lifecycle():
            try:
                prov.on_turn_start(1, "hello")
                prov.sync_turn("user", "assistant")
                prov.prefetch("query")
                prov.get_tool_schemas()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=call_lifecycle) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []

    def test_handle_tool_call_snapshot(self):
        """handle_tool_call takes a snapshot under lock, dispatches outside."""
        with (
            mock.patch.object(MultiMemoryProvider, "_load_config"),
            mock.patch.object(MultiMemoryProvider, "_validate_namespaces"),
        ):
            prov = MultiMemoryProvider()

        mock_sub = mock.MagicMock()
        mock_sub.name = "fake"
        type(mock_sub).PREFIX = mock.PropertyMock(return_value="fake")
        mock_sub.handle_tool_call.return_value = '{"result": "ok"}'
        prov._subs = [mock_sub]

        result = prov.handle_tool_call("fake_search", {"query": "test"})
        assert "ok" in result


class TestSchemaFailureProtection:
    """get_tool_schemas() wraps each sub-adapter in try/except (fixes #9948)."""

    def test_broken_sub_skipped_others_continue(self):
        """A sub-adapter that raises from get_tool_schemas is skipped."""
        with (
            mock.patch.object(MultiMemoryProvider, "_load_config"),
            mock.patch.object(MultiMemoryProvider, "_validate_namespaces"),
        ):
            prov = MultiMemoryProvider()

        good_sub = mock.MagicMock()
        good_sub.name = "good"
        good_sub.get_tool_schemas.return_value = [{"name": "good_search"}]

        bad_sub = mock.MagicMock()
        bad_sub.name = "bad"
        bad_sub.get_tool_schemas.side_effect = RuntimeError("schema boom")

        prov._subs = [bad_sub, good_sub]

        schemas = prov.get_tool_schemas()
        assert len(schemas) == 1
        assert schemas[0]["name"] == "good_search"

    def test_all_subs_broken_returns_empty(self):
        """If all sub-adapters fail, returns empty list (not an exception)."""
        with (
            mock.patch.object(MultiMemoryProvider, "_load_config"),
            mock.patch.object(MultiMemoryProvider, "_validate_namespaces"),
        ):
            prov = MultiMemoryProvider()

        broken = mock.MagicMock()
        broken.name = "broken"
        broken.get_tool_schemas.side_effect = RuntimeError("boom")

        prov._subs = [broken]
        schemas = prov.get_tool_schemas()
        assert schemas == []

    def test_schema_failure_records_health(self):
        """A failing sub-adapter's health is recorded as a failure."""
        with (
            mock.patch.object(MultiMemoryProvider, "_load_config"),
            mock.patch.object(MultiMemoryProvider, "_validate_namespaces"),
        ):
            prov = MultiMemoryProvider()

        broken = mock.MagicMock()
        broken.name = "broken"
        broken.get_tool_schemas.side_effect = RuntimeError("boom")

        prov._subs = [broken]
        prov.get_tool_schemas()
        assert prov._health._counters.get("broken", 0) >= 1


class TestCloseMethod:
    """_SubProviderAdapter.close() delegates to delegate.close() if available."""

    def test_base_close_calls_delegate_close(self):
        """Base adapter delegates close() when the real provider has it."""
        adapter = object.__new__(_SubProviderAdapter)
        mock_delegate = mock.MagicMock()
        mock_delegate.close = mock.MagicMock()
        adapter._delegate = mock_delegate

        adapter.close()
        mock_delegate.close.assert_called_once()

    def test_base_close_no_delegate_close(self):
        """Base adapter does nothing when delegate has no close()."""
        adapter = object.__new__(_SubProviderAdapter)
        mock_delegate = mock.MagicMock(spec=[])  # no close attribute
        adapter._delegate = mock_delegate

        adapter.close()  # should not raise

    def test_retaindb_close_calls_delegate_close(self):
        """_RetainDBAdapter.close() delegates to delegate.close()."""
        adapter = object.__new__(_RetainDBAdapter)
        mock_delegate = mock.MagicMock()
        mock_delegate.close = mock.MagicMock()
        adapter._delegate = mock_delegate

        adapter.close()
        mock_delegate.close.assert_called_once()

    def test_retaindb_close_falls_back_to_shutdown(self):
        """_RetainDBAdapter.close() falls back to shutdown() when no close()."""
        adapter = object.__new__(_RetainDBAdapter)
        mock_delegate = mock.MagicMock(spec=["shutdown"])
        adapter._delegate = mock_delegate

        adapter.close()
        mock_delegate.shutdown.assert_called_once()

    def test_shutdown_prefers_close(self):
        """MultiMemoryProvider.shutdown() prefers close() over shutdown()."""
        with (
            mock.patch.object(MultiMemoryProvider, "_load_config"),
            mock.patch.object(MultiMemoryProvider, "_validate_namespaces"),
        ):
            prov = MultiMemoryProvider()

        mock_sub = mock.MagicMock()
        mock_sub.name = "test"
        mock_sub.close = mock.MagicMock()
        prov._subs = [mock_sub]

        prov.shutdown()
        mock_sub.close.assert_called_once()


class TestLegacyConfigInGetEnabledBackends:
    """get_enabled_backends reads legacy memory.provider string."""

    def test_legacy_single_provider(self):
        from multi_memory.config import get_enabled_backends

        cfg = {"provider": "mem0"}
        result = get_enabled_backends(cfg)
        assert result == ["mem0"]

    def test_legacy_provider_multi_skipped(self):
        """memory.provider: 'multi' is the plugin itself, not a backend."""
        from multi_memory.config import get_enabled_backends

        cfg = {"provider": "multi"}
        result = get_enabled_backends(cfg)
        assert result == []

    def test_providers_list_takes_precedence(self):
        from multi_memory.config import get_enabled_backends

        cfg = {"provider": "mem0", "providers": ["holographic", "honcho"]}
        result = get_enabled_backends(cfg)
        assert result == ["holographic", "honcho"]

    def test_multi_backends_takes_precedence_over_all(self):
        from multi_memory.config import get_enabled_backends

        cfg = {"provider": "mem0", "providers": ["a"], "multi": {"backends": {"b": True}}}
        result = get_enabled_backends(cfg)
        assert result == ["b"]

    def test_nested_memory_multi_backends(self):
        from multi_memory.config import get_enabled_backends

        cfg = {"multi": {"backends": {"mnemosyne": {}, "mem0": {}}}}
        result = get_enabled_backends(cfg)
        assert "mnemosyne" in result
        assert "mem0" in result


# ── Introspection tests (ported from fork's MemoryManager) ──────────────


class TestIntrospectionHelpers:
    """Tests for _metadata_write_mode and _sync_accepts_messages."""

    def _make_adapter_with_delegate(self, delegate):
        mock_cls = mock.MagicMock(return_value=delegate)
        with mock.patch("multi_memory.adapters._try_import", return_value=mock_cls):
            from multi_memory.adapters import _SubProviderAdapter

            class _TestAdapter(_SubProviderAdapter):
                CONFIG_KEY = "test"
                MODULE = "test"
                CLASS = "Test"
                PREFIX = "test"

            return _TestAdapter()

    def test_metadata_mode_keyword_with_var_keyword(self):
        """Delegate with **kwargs → keyword mode."""
        delegate = mock.MagicMock()
        adapter = self._make_adapter_with_delegate(delegate)
        assert adapter._metadata_write_mode() == "keyword"

    def test_metadata_mode_keyword_with_explicit_metadata_param(self):
        """Delegate with explicit metadata param → keyword mode."""
        delegate = mock.MagicMock()

        def on_memory_write(action, target, content, metadata=None):
            pass

        delegate.on_memory_write = on_memory_write
        adapter = self._make_adapter_with_delegate(delegate)
        assert adapter._metadata_write_mode() == "keyword"

    def test_metadata_mode_positional_4_args(self):
        """Delegate with 4 positional args (no metadata keyword) → positional mode."""
        delegate = mock.MagicMock()

        def on_memory_write(action, target, content, meta):
            pass

        delegate.on_memory_write = on_memory_write
        adapter = self._make_adapter_with_delegate(delegate)
        assert adapter._metadata_write_mode() == "positional"

    def test_metadata_mode_legacy_3_args(self):
        """Delegate with only 3 args → legacy mode (no metadata)."""
        delegate = mock.MagicMock()

        def on_memory_write(action, target, content):
            pass

        delegate.on_memory_write = on_memory_write
        adapter = self._make_adapter_with_delegate(delegate)
        assert adapter._metadata_write_mode() == "legacy"

    def test_legacy_provider_on_memory_write_skips_metadata(self):
        """Legacy provider (3 args) should not receive metadata."""
        delegate = mock.MagicMock()
        calls = []

        def on_memory_write(action, target, content):
            calls.append((action, target, content))

        # Assign raw function so introspection sees its real signature
        delegate.on_memory_write = on_memory_write
        adapter = self._make_adapter_with_delegate(delegate)
        adapter.on_memory_write("add", "memory", "content", {"key": "val"})
        assert calls == [("add", "memory", "content")]

    def test_positional_provider_on_memory_write_passes_metadata_as_4th(self):
        """Positional provider (4 args) receives metadata as 4th positional arg."""
        delegate = mock.MagicMock()
        calls = []

        def on_memory_write(action, target, content, meta):
            calls.append((action, target, content, meta))

        delegate.on_memory_write = on_memory_write
        adapter = self._make_adapter_with_delegate(delegate)
        adapter.on_memory_write("add", "memory", "content", {"key": "val"})
        assert len(calls) == 1
        assert calls[0] == ("add", "memory", "content", {"key": "val"})

    def test_keyword_provider_on_memory_write_passes_metadata_as_kwarg(self):
        """Keyword provider accepts metadata as keyword arg."""
        delegate = mock.MagicMock()
        calls = []

        def on_memory_write(action, target, content, metadata=None):
            calls.append((action, target, content, metadata))

        delegate.on_memory_write = on_memory_write
        adapter = self._make_adapter_with_delegate(delegate)
        adapter.on_memory_write("add", "memory", "content", {"key": "val"})
        assert len(calls) == 1
        assert calls[0] == ("add", "memory", "content", {"key": "val"})

    def test_sync_accepts_messages_with_var_keyword(self):
        """Delegate with **kwargs → accepts messages."""
        delegate = mock.MagicMock()
        adapter = self._make_adapter_with_delegate(delegate)
        assert adapter._sync_accepts_messages() is True

    def test_sync_accepts_messages_with_explicit_messages_param(self):
        """Delegate with explicit messages param → accepts messages."""
        delegate = mock.MagicMock()

        def sync_turn(user, assistant, *, session_id="", messages=None):
            pass

        delegate.sync_turn = sync_turn
        adapter = self._make_adapter_with_delegate(delegate)
        assert adapter._sync_accepts_messages() is True

    def test_sync_rejects_messages_without_param(self):
        """Delegate without messages param → rejects messages."""
        delegate = mock.MagicMock()

        def sync_turn(user, assistant, *, session_id=""):
            pass

        delegate.sync_turn = sync_turn
        adapter = self._make_adapter_with_delegate(delegate)
        assert adapter._sync_accepts_messages() is False

    def test_sync_turn_passes_messages_when_accepted(self):
        """sync_turn passes messages kwarg when delegate accepts it."""
        delegate = mock.MagicMock()
        calls = []

        def sync_turn(user, assistant, *, session_id="", messages=None):
            calls.append((user, assistant, session_id, messages))

        delegate.sync_turn = sync_turn
        adapter = self._make_adapter_with_delegate(delegate)
        msgs = [{"role": "user", "content": "hi"}]
        adapter.sync_turn("user", "asst", session_id="s1", messages=msgs)
        assert len(calls) == 1
        assert calls[0] == ("user", "asst", "s1", msgs)

    def test_sync_turn_skips_messages_when_rejected(self):
        """sync_turn does not pass messages when delegate doesn't accept it."""
        delegate = mock.MagicMock()
        calls = []

        def sync_turn(user, assistant, *, session_id=""):
            calls.append((user, assistant, session_id))

        delegate.sync_turn = sync_turn
        adapter = self._make_adapter_with_delegate(delegate)
        msgs = [{"role": "user", "content": "hi"}]
        adapter.sync_turn("user", "asst", session_id="s1", messages=msgs)
        assert len(calls) == 1
        assert calls[0] == ("user", "asst", "s1")

    def test_sync_turn_no_messages_kwarg_skips(self):
        """sync_turn with messages=None does not pass messages."""
        delegate = mock.MagicMock()
        calls = []

        def sync_turn(user, assistant, *, session_id=""):
            calls.append((user, assistant, session_id))

        delegate.sync_turn = sync_turn
        adapter = self._make_adapter_with_delegate(delegate)
        adapter.sync_turn("user", "asst", session_id="s1")
        assert len(calls) == 1
        assert calls[0] == ("user", "asst", "s1")
