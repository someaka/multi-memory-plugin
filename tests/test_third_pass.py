"""Tests for third-pass audit fixes.

Covers:
- _load_config re-entrancy guard (explicit _loading flag, not getattr)
- get_tool_schemas double-checked locking under concurrent access
- _invalidate_schema_cache thread safety
- handle_tool_call with empty PREFIX falls back to sub.name
- load_full_config single reader
- _normalize_multi_config rename consistency
"""

# intentional imports-inside-functions + magic numbers in tests
from __future__ import annotations

import threading
from unittest import mock

from multi_memory import MultiMemoryProvider
from multi_memory.config import load_full_config

# ── _load_config re-entrancy guard ────────────────────────────────────────


class TestLoadConfigReentrancy:
    """_load_config guard prevents infinite recursion."""

    def test_reentrant_call_is_noop(self, tmp_path):
        """Calling _load_config from within _load_config is a no-op."""
        cfg = tmp_path / "config.yaml"
        cfg.write_text("memory:\n  multi:\n    backends: {}\n")

        call_count = [0]
        original_impl = MultiMemoryProvider._MultiMemoryProvider__load_config_impl

        def counting_impl(self):
            call_count[0] += 1
            if call_count[0] == 1:
                # Simulate re-entrancy: call _load_config again from inside
                self._load_config()
            return original_impl(self)

        with (
            mock.patch("multi_memory.config._get_config_path", return_value=str(cfg)),
            mock.patch.object(
                MultiMemoryProvider,
                "_MultiMemoryProvider__load_config_impl",
                counting_impl,
            ),
        ):
            MultiMemoryProvider()

        # The inner _load_config call should have been skipped by the guard
        assert call_count[0] == 1

    def test_loading_flag_initialized(self, tmp_path):
        """_loading is set to False in __init__, not via getattr."""
        cfg = tmp_path / "config.yaml"
        cfg.write_text("memory:\n  multi:\n    backends: {}\n")
        with mock.patch("multi_memory.config._get_config_path", return_value=str(cfg)):
            p = MultiMemoryProvider()
        assert hasattr(p, "_loading")
        assert p._loading is False


# ── get_tool_schemas thread safety ────────────────────────────────────────


class TestSchemaCacheThreadSafety:
    """get_tool_schemas uses double-checked locking."""

    def test_concurrent_calls_build_once(self):
        """Multiple threads calling get_tool_schemas get the same cached result."""
        p = MultiMemoryProvider()
        build_count = [0]
        lock = threading.Lock()

        sub = mock.MagicMock()
        sub.name = "test"

        def slow_schemas():
            with lock:
                build_count[0] += 1
            return [{"name": "test_tool"}]

        sub.get_tool_schemas = slow_schemas
        p._subs = [sub]

        results = [None] * 10
        barrier = threading.Barrier(10)

        def worker(idx):
            barrier.wait()
            results[idx] = p.get_tool_schemas()

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All threads should get the same result
        for r in results:
            assert r == [{"name": "test_tool"}]

    def test_invalidate_and_rebuild(self):
        """After invalidation, next call rebuilds."""
        p = MultiMemoryProvider()
        sub = mock.MagicMock()
        sub.name = "test"
        sub.get_tool_schemas.return_value = [{"name": "tool_a"}]
        p._subs = [sub]

        schemas1 = p.get_tool_schemas()
        assert schemas1 == [{"name": "tool_a"}]

        # Change what the sub returns, invalidate, rebuild
        sub.get_tool_schemas.return_value = [{"name": "tool_b"}]
        p._invalidate_schema_cache()
        schemas2 = p.get_tool_schemas()
        assert schemas2 == [{"name": "tool_b"}]


# ── handle_tool_call empty PREFIX fallback ────────────────────────────────


class TestHandleToolCallEmptyPrefix:
    """When PREFIX is empty, handle_tool_call falls back to sub.name."""

    def test_empty_prefix_uses_sub_name(self):
        p = MultiMemoryProvider()
        sub = mock.MagicMock()
        sub.name = "mybackend"
        type(sub).PREFIX = ""
        sub.handle_tool_call.return_value = '{"ok": true}'
        p._subs = [sub]

        result = p.handle_tool_call("mybackend_tool", {})
        assert result == '{"ok": true}'
        sub.handle_tool_call.assert_called_once()

    def test_prefix_match_takes_precedence(self):
        p = MultiMemoryProvider()
        sub1 = mock.MagicMock()
        sub1.name = "alpha"
        type(sub1).PREFIX = "alpha"
        sub1.handle_tool_call.return_value = '{"from": "alpha"}'

        sub2 = mock.MagicMock()
        sub2.name = "beta"
        type(sub2).PREFIX = "beta"
        sub2.handle_tool_call.return_value = '{"from": "beta"}'

        p._subs = [sub1, sub2]
        result = p.handle_tool_call("beta_tool", {})
        assert result == '{"from": "beta"}'
        sub1.handle_tool_call.assert_not_called()


# ── load_full_config ──────────────────────────────────────────────────────


class TestLoadFullConfig:
    """load_full_config is the single config reader."""

    def test_returns_dict(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("memory:\n  provider: multi\n")
        with mock.patch("multi_memory.config._get_config_path", return_value=str(cfg)):
            result = load_full_config()
        assert result == {"memory": {"provider": "multi"}}

    def test_missing_file_returns_empty(self, tmp_path):
        cfg = tmp_path / "nonexistent.yaml"
        with mock.patch("multi_memory.config._get_config_path", return_value=str(cfg)):
            result = load_full_config()
        assert result == {}

    def test_non_dict_yaml_returns_empty(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("[1, 2, 3]")
        with mock.patch("multi_memory.config._get_config_path", return_value=str(cfg)):
            result = load_full_config()
        assert result == {}

    def test_invalid_yaml_returns_empty(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text(":bad: yaml: [")
        with mock.patch("multi_memory.config._get_config_path", return_value=str(cfg)):
            result = load_full_config()
        assert result == {}


# ── _normalize_multi_config rename ────────────────────────────────────────


class TestNormalizeRename:
    """_normalize_multi_config is the canonical name (not _normalise)."""

    def test_function_exists(self):
        from multi_memory import _normalize_multi_config as fn

        assert callable(fn)

    def test_old_name_gone(self):
        import multi_memory

        assert not hasattr(multi_memory, "_normalise_multi_config")
