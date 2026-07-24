"""Tests for multi_memory.discovery — backend discovery and installation detection."""

# magic numbers in tests are normal
from __future__ import annotations

from unittest import mock

from multi_memory.discovery import (
    _BACKEND_REGISTRY,
    _is_mnemosyne_plugin_installed,
    discover_backends,
    installed_backends,
)


def _mnemosyne_plugin_available() -> bool:
    """Check if the Mnemosyne user-installed plugin exists."""
    return _is_mnemosyne_plugin_installed()


class TestBackendRegistry:
    """The registry has the expected backend entries."""

    def test_nine_known_backends(self):
        assert len(_BACKEND_REGISTRY) == 9

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

    def test_contains_openviking(self):
        keys = [e[0] for e in _BACKEND_REGISTRY]
        assert "openviking" in keys

    def test_contains_hindsight(self):
        keys = [e[0] for e in _BACKEND_REGISTRY]
        assert "hindsight" in keys

    def test_contains_retaindb(self):
        keys = [e[0] for e in _BACKEND_REGISTRY]
        assert "retaindb" in keys

    def test_contains_byterover(self):
        keys = [e[0] for e in _BACKEND_REGISTRY]
        assert "byterover" in keys

    def test_contains_supermemory(self):
        keys = [e[0] for e in _BACKEND_REGISTRY]
        assert "supermemory" in keys

    def test_mnemosyne_label_is_plugin(self):
        entry = next(e for e in _BACKEND_REGISTRY if e[0] == "mnemosyne")
        assert "plugin" in entry[2].lower()


class TestDiscoverBackends:
    """discover_backends() probes each backend module."""

    def test_returns_list_of_dicts(self):
        results = discover_backends()
        assert isinstance(results, list)
        assert len(results) == 9
        for entry in results:
            assert isinstance(entry, dict)
            assert "config_key" in entry
            assert "module" in entry
            assert "label" in entry
            assert "installed" in entry

    def test_mnemosyne_uses_plugin_check(self):
        """Mnemosyne uses _is_mnemosyne_plugin_installed, not find_spec."""
        with mock.patch(
            "multi_memory.discovery._is_mnemosyne_plugin_installed",
            return_value=True,
        ):
            results = discover_backends()
        mnemosyne = next(r for r in results if r["config_key"] == "mnemosyne")
        assert mnemosyne["installed"] is True

    def test_mnemosyne_not_installed_when_plugin_missing(self):
        with mock.patch(
            "multi_memory.discovery._is_mnemosyne_plugin_installed",
            return_value=False,
        ):
            results = discover_backends()
        mnemosyne = next(r for r in results if r["config_key"] == "mnemosyne")
        assert mnemosyne["installed"] is False

    def test_installed_flag_false_for_unavailable(self):
        """Backend with non-installed module reports installed=False."""
        with (
            mock.patch("multi_memory.discovery.find_spec", return_value=None),
            mock.patch(
                "multi_memory.discovery._is_mnemosyne_plugin_installed",
                return_value=False,
            ),
        ):
            results = discover_backends()
        for entry in results:
            assert entry["installed"] is False

    def test_find_spec_called_for_non_mnemosyne_backends(self):
        """discover_backends calls find_spec for all 8 non-mnemosyne backends."""
        with (
            mock.patch(
                "multi_memory.discovery._is_mnemosyne_plugin_installed",
                return_value=False,
            ),
            mock.patch("multi_memory.discovery.find_spec") as mock_fs,
        ):
            mock_fs.return_value = mock.MagicMock()
            discover_backends()
        expected_calls = [
            mock.call("plugins.memory.mem0"),
            mock.call("plugins.memory.holographic"),
            mock.call("plugins.memory.honcho"),
            mock.call("plugins.memory.openviking"),
            mock.call("plugins.memory.hindsight"),
            mock.call("plugins.memory.retaindb"),
            mock.call("plugins.memory.byterover"),
            mock.call("plugins.memory.supermemory"),
        ]
        mock_fs.assert_has_calls(expected_calls, any_order=False)

    def test_individual_install_detection(self):
        """Each backend is independently checked."""

        def find_spec_side_effect(module):
            if module == "plugins.memory.holographic":
                return mock.MagicMock()
            if module == "plugins.memory.openviking":
                return mock.MagicMock()
            return None

        with (
            mock.patch(
                "multi_memory.discovery._is_mnemosyne_plugin_installed",
                return_value=False,
            ),
            mock.patch(
                "multi_memory.discovery.find_spec",
                side_effect=find_spec_side_effect,
            ),
        ):
            results = discover_backends()

        mnemosyne = next(r for r in results if r["config_key"] == "mnemosyne")
        holographic = next(r for r in results if r["config_key"] == "holographic")
        openviking = next(r for r in results if r["config_key"] == "openviking")
        mem0 = next(r for r in results if r["config_key"] == "mem0")
        assert mnemosyne["installed"] is False
        assert holographic["installed"] is True
        assert openviking["installed"] is True
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

    def test_includes_mnemosyne_when_plugin_exists(self):
        with (
            mock.patch(
                "multi_memory.discovery._is_mnemosyne_plugin_installed",
                return_value=True,
            ),
            mock.patch(
                "multi_memory.discovery.find_spec",
                return_value=None,
            ),
        ):
            result = installed_backends()
        assert "mnemosyne" in result

    def test_empty_when_none_installed(self):
        with (
            mock.patch("multi_memory.discovery.find_spec", return_value=None),
            mock.patch(
                "multi_memory.discovery._is_mnemosyne_plugin_installed",
                return_value=False,
            ),
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


class TestIsMnemosynePluginInstalled:
    """_is_mnemosyne_plugin_installed() detects the plugin directory."""

    def test_hermes_mnemosyne_name_detected(self, tmp_path, monkeypatch):
        plugins_dir = tmp_path / "plugins" / "hermes-mnemosyne"
        plugins_dir.mkdir(parents=True)
        (plugins_dir / "__init__.py").write_text("")
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        assert _is_mnemosyne_plugin_installed() is True

    def test_mnemosyne_name_detected(self, tmp_path, monkeypatch):
        plugins_dir = tmp_path / "plugins" / "mnemosyne"
        plugins_dir.mkdir(parents=True)
        (plugins_dir / "__init__.py").write_text("")
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        assert _is_mnemosyne_plugin_installed() is True

    def test_not_installed_when_missing(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        assert _is_mnemosyne_plugin_installed() is False

    def test_directory_but_no_init(self, tmp_path, monkeypatch):
        plugins_dir = tmp_path / "plugins" / "mnemosyne"
        plugins_dir.mkdir(parents=True)
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        assert _is_mnemosyne_plugin_installed() is False

    def test_find_spec_module_not_found_handled(self):
        with mock.patch("multi_memory.discovery.find_spec", side_effect=ModuleNotFoundError):
            results = discover_backends()
        assert len(results) == 9
