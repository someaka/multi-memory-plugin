"""Tests for multi_memory.discovery — backend discovery and installation detection."""
from __future__ import annotations

from unittest import mock

import pytest

from multi_memory.discovery import (
    _BACKEND_REGISTRY,
    discover_backends,
    installed_backends,
)


def _mnemosyne_available() -> bool:
    """Check if the mnemosyne module is actually importable in this environment."""
    from importlib.util import find_spec
    return find_spec("mnemosyne") is not None


class TestBackendRegistry:
    """The registry has the expected backend entries."""

    def test_four_known_backends(self):
        assert len(_BACKEND_REGISTRY) == 4

    def test_contains_mnemosyne(self):
        keys = [e[0] for e in _BACKEND_REGISTRY]
        assert "mnemosyne" in keys

    def test_contains_mem0(self):
        keys = [e[0] for e in _BACKEND_REGISTRY]
        assert "mem0" in keys

    def test_contains_holographic(self):
        keys = [e[0] for e in _BACKEND_REGISTRY]
        assert "holographic" in keys

    def test_contains_honcho(self):
        keys = [e[0] for e in _BACKEND_REGISTRY]
        assert "honcho" in keys


class TestDiscoverBackends:
    """discover_backends() probes each backend module."""

    def test_returns_list_of_dicts(self):
        results = discover_backends()
        assert isinstance(results, list)
        assert len(results) == 4
        for entry in results:
            assert isinstance(entry, dict)
            assert "config_key" in entry
            assert "module" in entry
            assert "label" in entry
            assert "installed" in entry

    def test_mnemosyne_is_installed(self):
        """mnemosyne is stdlib-backed (our package provides it)."""
        if not _mnemosyne_available():
            pytest.skip("mnemosyne is not installed in this environment")
        results = discover_backends()
        mnemosyne = next(r for r in results if r["config_key"] == "mnemosyne")
        assert mnemosyne["installed"] is True

    def test_installed_flag_true_for_available(self):
        """Backend with installed module reports installed=True."""
        if not _mnemosyne_available():
            pytest.skip("mnemosyne is not installed in this environment")
        results = discover_backends()
        for entry in results:
            if entry["config_key"] == "mnemosyne":
                assert entry["installed"] is True

    def test_installed_flag_false_for_unavailable(self):
        """Backend with non-installed module reports installed=False."""
        with mock.patch(
            "multi_memory.discovery.find_spec", return_value=None
        ):
            results = discover_backends()
        for entry in results:
            assert entry["installed"] is False

    def test_find_spec_called_with_module_paths(self):
        """discover_backends calls find_spec for each module_path."""
        with mock.patch("multi_memory.discovery.find_spec") as mock_fs:
            mock_fs.return_value = mock.MagicMock()
            discover_backends()
        expected_calls = [
            mock.call("mnemosyne"),
            mock.call("plugins.memory.mem0"),
            mock.call("plugins.memory.holographic"),
            mock.call("plugins.memory.honcho"),
        ]
        mock_fs.assert_has_calls(expected_calls, any_order=False)

    def test_individual_install_detection(self):
        """Each backend is independently checked."""
        def find_spec_side_effect(module):
            if module == "mnemosyne":
                return mock.MagicMock()
            return None

        with mock.patch(
            "multi_memory.discovery.find_spec",
            side_effect=find_spec_side_effect,
        ):
            results = discover_backends()

        mnemosyne = next(r for r in results if r["config_key"] == "mnemosyne")
        mem0 = next(r for r in results if r["config_key"] == "mem0")
        assert mnemosyne["installed"] is True
        assert mem0["installed"] is False

    def test_result_order_matches_registry(self):
        results = discover_backends()
        for i, (key, module, label) in enumerate(_BACKEND_REGISTRY):
            assert results[i]["config_key"] == key
            assert results[i]["module"] == module
            assert results[i]["label"] == label


class TestInstalledBackends:
    """installed_backends() returns config_keys for available backends."""

    def test_returns_list_of_strings(self):
        result = installed_backends()
        assert isinstance(result, list)
        if result:
            assert all(isinstance(k, str) for k in result)

    def test_includes_mnemosyne(self):
        """mnemosyne may not be the installed package — check with mock."""
        with mock.patch(
            "multi_memory.discovery.find_spec",
            side_effect=lambda m: mock.MagicMock() if m == "mnemosyne" else None,
        ):
            result = installed_backends()
        assert "mnemosyne" in result

    def test_empty_when_none_installed(self):
        with mock.patch(
            "multi_memory.discovery.find_spec", return_value=None
        ):
            result = installed_backends()
        assert result == []

    def test_delegates_to_discover_backends(self):
        """installed_backends filters discover_backends results."""
        with mock.patch(
            "multi_memory.discovery.discover_backends",
            return_value=[
                {"config_key": "a", "installed": True},
                {"config_key": "b", "installed": False},
                {"config_key": "c", "installed": True},
            ],
        ):
            result = installed_backends()
        assert result == ["a", "c"]
