"""Tests for audit pass 7 fixes.

Covers:
- _is_disabled recognizes "off"/"disabled" (case-insensitive)
- _set_active_backends coerces non-dict multi/backends instead of crashing
- _cmd_setup_wizard guards against non-dict config["memory"]
- _cmd_setup_backend guards against non-dict config["memory"]
"""

from __future__ import annotations

from unittest import mock

from multi_memory.config import _is_disabled


class TestIsDisabledOffDisabled:
    """_is_disabled now recognizes 'off' and 'disabled' strings."""

    def test_off_disabled(self):
        assert _is_disabled("off") is True

    def test_uppercase_off_disabled(self):
        assert _is_disabled("OFF") is True

    def test_mixed_case_off_disabled(self):
        assert _is_disabled("Off") is True

    def test_disabled_string(self):
        assert _is_disabled("disabled") is True

    def test_uppercase_disabled(self):
        assert _is_disabled("DISABLED") is True

    def test_mixed_case_disabled(self):
        assert _is_disabled("Disabled") is True

    def test_off_with_whitespace(self):
        assert _is_disabled("  off  ") is True

    def test_disabled_with_whitespace(self):
        assert _is_disabled("  disabled  ") is True

    def test_on_still_enabled(self):
        assert _is_disabled("on") is False

    def test_enabled_still_enabled(self):
        assert _is_disabled("enabled") is False


class TestSetActiveBackendsNonDictGuards:
    """_set_active_backends coerces non-dict multi/backends instead of crashing."""

    def test_non_dict_multi_coerced(self):
        """When memory_cfg['multi'] is a string, it's coerced to a dict."""
        from multi_memory.cli import _set_active_backends

        memory_cfg: dict = {"multi": "not-a-dict"}
        _set_active_backends(memory_cfg, ["mnemosyne"])
        assert isinstance(memory_cfg["multi"], dict)
        assert isinstance(memory_cfg["multi"]["backends"], dict)
        assert "mnemosyne" in memory_cfg["multi"]["backends"]

    def test_non_dict_backends_coerced(self):
        """When backends is a string, it's coerced to a dict."""
        from multi_memory.cli import _set_active_backends

        memory_cfg: dict = {"multi": {"backends": "not-a-dict"}}
        _set_active_backends(memory_cfg, ["mnemosyne"])
        assert isinstance(memory_cfg["multi"]["backends"], dict)
        assert "mnemosyne" in memory_cfg["multi"]["backends"]

    def test_non_dict_multi_is_int(self):
        """When memory_cfg['multi'] is an int, it's coerced to a dict."""
        from multi_memory.cli import _set_active_backends

        memory_cfg: dict = {"multi": 123}
        _set_active_backends(memory_cfg, ["holographic"])
        assert isinstance(memory_cfg["multi"], dict)
        assert "holographic" in memory_cfg["multi"]["backends"]

    def test_non_dict_multi_is_list(self):
        """When memory_cfg['multi'] is a list, it's coerced to a dict."""
        from multi_memory.cli import _set_active_backends

        memory_cfg: dict = {"multi": [1, 2, 3]}
        _set_active_backends(memory_cfg, ["mem0"])
        assert isinstance(memory_cfg["multi"], dict)
        assert "mem0" in memory_cfg["multi"]["backends"]

    def test_non_dict_backends_is_list(self):
        """When backends is a list, it's coerced to a dict."""
        from multi_memory.cli import _set_active_backends

        memory_cfg: dict = {"multi": {"backends": [1, 2]}}
        _set_active_backends(memory_cfg, ["mnemosyne"])
        assert isinstance(memory_cfg["multi"]["backends"], dict)
        assert "mnemosyne" in memory_cfg["multi"]["backends"]

    def test_existing_dict_backends_preserved(self):
        """Normal dict case still works — existing backends preserved."""
        from multi_memory.cli import _set_active_backends

        memory_cfg: dict = {"multi": {"backends": {"mem0": {"api_key": "k"}}}}
        _set_active_backends(memory_cfg, ["mem0", "mnemosyne"])
        assert "mem0" in memory_cfg["multi"]["backends"]
        assert "mnemosyne" in memory_cfg["multi"]["backends"]
        # Existing config preserved
        assert memory_cfg["multi"]["backends"]["mem0"] == {"api_key": "k"}


class TestSetCmdSetupWizardNonDictMemory:
    """_cmd_setup_wizard guards against non-dict config['memory'].

    Previously used config.setdefault("memory", {}) which returns the
    pre-existing non-dict value if 'memory' is a string, causing downstream
    AttributeError when _get_active_backends tries .get() on it.
    """

    def test_non_dict_memory_does_not_crash(self):
        """When config['memory'] is a string, wizard coerces to dict."""
        import argparse

        from multi_memory.cli import _cmd_setup_wizard

        config = {"memory": "corrupt-string"}
        args = argparse.Namespace()
        # _cmd_setup_wizard is pragma:no cover (interactive), but the
        # config coercion happens before any curses interaction, so we
        # test up to the point where it would enter the picker
        with (
            mock.patch("multi_memory.cli.load_config", return_value=config),
            mock.patch("multi_memory.cli._get_available_backends", return_value=[]),
        ):
            # With no backends discovered, it returns early — but the
            # config coercion already happened at the top
            _cmd_setup_wizard(args)


class TestSetCmdSetupBackendNonDictMemory:
    """_cmd_setup_backend guards against non-dict config['memory']."""

    def test_non_dict_memory_does_not_crash_before_match(self):
        """When config['memory'] is non-dict, setup_backend coerces before _do_backend_setup."""
        from multi_memory.cli import _cmd_setup_backend

        config = {"memory": 12345}
        with (
            mock.patch("multi_memory.cli.load_config", return_value=config),
            mock.patch(
                "multi_memory.cli._get_available_backends",
                return_value=[("mnemosyne", "local", None)],
            ),
            mock.patch("multi_memory.cli._do_backend_setup") as mock_setup,
        ):
            _cmd_setup_backend("mnemosyne")
            mock_setup.assert_called_once()


class TestMaskedSuffixLen:
    """The _MASKED_SUFFIX_LEN constant exists and is used for secret masking."""

    def test_constant_exists(self):
        from multi_memory.cli import _MASKED_SUFFIX_LEN

        assert _MASKED_SUFFIX_LEN == 4
