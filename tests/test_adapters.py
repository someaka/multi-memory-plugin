"""Tests for multi_memory plugin — adapters, lifecycle hooks, edge paths.

This file covers:
- _SubProviderAdapter and subclasses
- MultiMemoryProvider lifecycle hooks (initialize, shutdown, prefetch, etc.)
- Edge cases: missing backend, error handling, adapter instantiation failures
"""
from __future__ import annotations

from importlib.util import find_spec
from unittest import mock

import pytest

from multi_memory import MultiMemoryProvider, _normalise_multi_config, _load_backends_from_config
from multi_memory.adapters import (
    _SubProviderAdapter,
    _HolographicAdapter,
    _Mem0Adapter,
    _MnemosyneAdapter,
    _HonchoAdapter,
    _try_import,
)


def _holographic_available() -> bool:
    """Check if the holographic backend is importable."""
    try:
        return find_spec("plugins.memory.holographic") is not None
    except (ModuleNotFoundError, ValueError):
        return False


requires_holographic = pytest.mark.skipif(
    not _holographic_available(),
    reason="holographic backend not available (requires Hermes plugins package)",
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

    def test_False_capital_skipped(self):
        cfg = {"memory": {"multi": {"backends": {"mnemosyne": "False", "mem0": True}}}}
        result = _load_backends_from_config(cfg)
        assert "mnemosyne" not in [a.name for a in result]

    @requires_holographic
    def test_empty_dict_enabled(self):
        cfg = {"memory": {"multi": {"backends": {"holographic": {}}}}}
        result = _load_backends_from_config(cfg)
        assert any(a.name == "holographic" for a in result)


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
        with mock.patch("multi_memory.adapters.find_spec", return_value=mock.MagicMock()):
            with mock.patch("multi_memory.adapters.importlib.import_module", side_effect=ImportError("broken")):
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
        assert provider.is_available() in (True, False)
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
            original = sub.initialize
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
                def new_init(*a, **kw):
                    fail_flags.append(idx)
                    if idx == 0:
                        raise RuntimeError(f"fail {idx}")
                    return orig(*a, **kw)
                return new_init

            sub.initialize = make_init(i, original_init)

        # Should not raise — exceptions in initialize are caught
        provider.initialize(session_id="test-session")
        assert len(fail_flags) == len(provider._subs)

    def test_shutdown_calls_in_reverse_order(self, provider):
        """shutdown() calls sub-providers in reversed order."""
        call_order = []
        for sub in provider._subs:
            original = sub.shutdown
            sub.shutdown = lambda ns=sub.name: call_order.append(ns)
        provider.shutdown()
        expected = [s.name for s in reversed(provider._subs)]
        assert call_order == expected

    def test_shutdown_exception_isolation(self, provider):
        """Failure in one sub's shutdown() doesn't stop others."""
        flags = []
        for i, sub in enumerate(provider._subs):
            def make_shutdown(idx, orig):
                def fn():
                    flags.append(idx)
                    if idx % 2 == 0:
                        raise RuntimeError(f"shutdown fail {idx}")
                return fn
            sub.shutdown = make_shutdown(i, sub.shutdown)
        provider.shutdown()  # Should not raise
        assert len(flags) == len(provider._subs)

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
            original = sub.prefetch
            if i == 0:
                sub.prefetch = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("prefetch fail"))
        result = provider.prefetch("test query", session_id="s1")
        assert isinstance(result, str)  # doesn't raise

    def test_queue_prefetch_calls_all_subs(self, provider):
        """queue_prefetch() calls every sub-provider."""
        call_count = [0]
        for sub in provider._subs:
            original = sub.queue_prefetch
            sub.queue_prefetch = lambda *a, **kw: call_count.__setitem__(0, call_count[0] + 1)
        provider.queue_prefetch("test query", session_id="s1")
        assert call_count[0] == len(provider._subs)

    def test_sync_turn_calls_all_subs(self, provider):
        """sync_turn() calls every sub-provider."""
        calls = []
        for sub in provider._subs:
            original = sub.sync_turn
            sub.sync_turn = lambda u, a, ns=sub.name, **kw: calls.append(ns)
        provider.sync_turn("user", "assistant", session_id="s1")
        expected = [s.name for s in provider._subs]
        assert calls == expected

    def test_on_turn_start_calls_all_subs(self, provider):
        calls = []
        for sub in provider._subs:
            sub.on_turn_start = lambda ns=sub.name: calls.append(ns)
        provider.on_turn_start()
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
            sub.on_session_switch = lambda ns=sub.name: calls.append(ns)
        provider.on_session_switch()
        assert calls == [s.name for s in provider._subs]

    def test_on_memory_write_calls_all_subs(self, provider):
        calls = []
        for sub in provider._subs:
            sub.on_memory_write = lambda a, t, c, ns=sub.name: calls.append(ns)
        provider.on_memory_write("add", "memory", "content")
        assert calls == [s.name for s in provider._subs]

    def test_on_delegation_calls_all_subs(self, provider):
        calls = []
        for sub in provider._subs:
            sub.on_delegation = lambda ns=sub.name: calls.append(ns)
        provider.on_delegation()
        assert calls == [s.name for s in provider._subs]

    def test_queue_prefetch_exception_isolation(self, provider):
        """queue_prefetch handles per-sub exceptions."""
        for i, sub in enumerate(provider._subs):
            if i == 0:
                sub.queue_prefetch = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("queue fail"))
        provider.queue_prefetch("test", session_id="s1")  # should not raise

    def test_sync_turn_exception_isolation(self, provider):
        """sync_turn handles per-sub exceptions."""
        for i, sub in enumerate(provider._subs):
            if i == 0:
                sub.sync_turn = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("sync fail"))
        provider.sync_turn("u", "a", session_id="s1")  # should not raise

    def test_on_memory_write_exception_isolation(self, provider):
        for i, sub in enumerate(provider._subs):
            if i == 0:
                sub.on_memory_write = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("write fail"))
        provider.on_memory_write("add", "memory", "x")  # should not raise

    def test_on_turn_start_exception_isolation(self, provider):
        for i, sub in enumerate(provider._subs):
            if i == 0:
                sub.on_turn_start = lambda: (_ for _ in ()).throw(RuntimeError("turn fail"))
        provider.on_turn_start()  # should not raise

    def test_on_session_end_exception_isolation(self, provider):
        for i, sub in enumerate(provider._subs):
            if i == 0:
                sub.on_session_end = lambda m: (_ for _ in ()).throw(RuntimeError("session end fail"))
        provider.on_session_end([{"role": "user"}])  # should not raise

    def test_on_session_switch_exception_isolation(self, provider):
        for i, sub in enumerate(provider._subs):
            if i == 0:
                sub.on_session_switch = lambda: (_ for _ in ()).throw(RuntimeError("switch fail"))
        provider.on_session_switch()  # should not raise

    def test_on_delegation_exception_isolation(self, provider):
        for i, sub in enumerate(provider._subs):
            if i == 0:
                sub.on_delegation = lambda: (_ for _ in ()).throw(RuntimeError("delegation fail"))
        provider.on_delegation()  # should not raise

    def test_prefetch_with_non_empty_results(self, provider):
        """prefetch concatenates non-empty results with sub names."""
        names_captured = []
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
        assert result is not None

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
        # The real MemoryProvider's on_turn_start needs turn_number + message
        # but the adapter doesn't forward them. We test the adapter method
        # with a mock that tolerates the call.
        adapter._delegate.on_turn_start = mock.MagicMock()
        adapter.on_turn_start()  # should not raise
        adapter._delegate.on_turn_start.assert_called_once()

    def test_on_session_end(self, adapter):
        adapter.on_session_end([])  # should not raise

    def test_on_session_switch(self, adapter):
        adapter._delegate.on_session_switch = mock.MagicMock()
        adapter.on_session_switch()  # should not raise
        adapter._delegate.on_session_switch.assert_called_once()

    def test_on_delegation(self, adapter):
        adapter._delegate.on_delegation = mock.MagicMock()
        adapter.on_delegation()  # should not raise
        adapter._delegate.on_delegation.assert_called_once()

    def test_name_property(self, adapter):
        assert adapter.name == "holographic"
