"""Unit tests for multi-memory plugin."""
from __future__ import annotations

import pytest
from multi_memory.adapters import (
    _SubProviderAdapter,
    _HolographicAdapter,
    _Mem0Adapter,
    _MnemosyneAdapter,
    _HonchoAdapter,
)
from multi_memory import (
    MultiMemoryProvider,
    _normalise_multi_config,
    _load_backends_from_config,
)


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

    def test_empty_dict_enabled(self):
        cfg = {"memory": {"multi": {"backends": {"holographic": {}}}}}
        result = _load_backends_from_config(cfg)
        assert any(a.name == "holographic" for a in result)


class TestMultiMemoryProvider:
    def test_name(self):
        p = MultiMemoryProvider()
        assert p.name == "multi"

    def test_auto_loads_backends(self):
        p = MultiMemoryProvider()
        assert p.is_available() in (True, False)
        names = [s.name for s in p._subs]
        assert "holographic" in names

    def test_get_tool_schemas_returns_prefixed(self):
        p = MultiMemoryProvider()
        schemas = p.get_tool_schemas()
        assert any("_" in s["name"] for s in schemas)

    def test_handle_tool_call_matches_schema(self):
        p = MultiMemoryProvider()
        schemas = p.get_tool_schemas()
        if schemas:
            result = p.handle_tool_call(schemas[0]["name"], {})
            assert "No sub-provider handles" not in result
