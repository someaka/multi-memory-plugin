"""Tests for the validate command and create_adapter helper."""

from unittest.mock import MagicMock, patch
import pytest

from multi_memory.cli import _cmd_validate, create_adapter


class TestCreateAdapter:
    """Tests for create_adapter helper function."""

    def test_create_unknown_backend(self):
        """Unknown backend returns None."""
        result = create_adapter("unknown_backend")
        assert result is None

    def test_create_mnemosyne_adapter(self):
        """Mnemosyne adapter can be created."""
        with patch("multi_memory.adapters._MnemosyneAdapter") as mock_adapter:
            mock_instance = MagicMock()
            mock_adapter.return_value = mock_instance
            result = create_adapter("mnemosyne")
            assert result == mock_instance

    def test_create_mem0_adapter(self):
        """Mem0 adapter can be created."""
        with patch("multi_memory.adapters._Mem0Adapter") as mock_adapter:
            mock_instance = MagicMock()
            mock_adapter.return_value = mock_instance
            result = create_adapter("mem0")
            assert result == mock_instance

    def test_create_adapter_import_error(self):
        """Import errors are handled gracefully."""
        with patch("builtins.__import__", side_effect=ImportError("No module")):
            result = create_adapter("mnemosyne")
            assert result is None

    def test_create_adapter_instantiation_error(self):
        """Instantiation errors are handled gracefully."""
        with patch("multi_memory.adapters._MnemosyneAdapter") as mock_adapter:
            mock_adapter.side_effect = RuntimeError("Failed to init")
            result = create_adapter("mnemosyne")
            assert result is None

    def test_create_all_supported_backends(self):
        """All supported backends can be created."""
        backend_to_class = {
            "mnemosyne": "_MnemosyneAdapter",
            "mem0": "_Mem0Adapter",
            "holographic": "_HolographicAdapter",
            "honcho": "_HonchoAdapter",
            "hindsight": "_HindsightAdapter",
            "openviking": "_OpenVikingAdapter",
            "retaindb": "_RetainDBAdapter",
            "byterover": "_ByteRoverAdapter",
            "supermemory": "_SupermemoryAdapter",
        }
        for backend, class_name in backend_to_class.items():
            with patch(f"multi_memory.adapters.{class_name}") as mock_adapter:
                mock_instance = MagicMock()
                mock_adapter.return_value = mock_instance
                result = create_adapter(backend)
                assert result == mock_instance, f"Failed to create {backend}"


class TestValidateCommand:
    """Tests for the validate command."""

    def test_validate_no_backends(self):
        """Validate with no active backends succeeds."""
        args = MagicMock()
        args.fix = False

        with patch("multi_memory.cli.load_config") as mock_load:
            mock_load.return_value = {"memory": {}}
            with patch("multi_memory.cli.get_enabled_backends") as mock_get:
                mock_get.return_value = []
                # Should not raise
                _cmd_validate(args)

    def test_validate_with_active_backends(self):
        """Validate with active backends checks each one."""
        args = MagicMock()
        args.fix = False

        with patch("multi_memory.cli.load_config") as mock_load:
            mock_load.return_value = {"memory": {"multi": {"backends": ["mnemosyne"]}}}
            with patch("multi_memory.cli.get_enabled_backends") as mock_get:
                mock_get.return_value = ["mnemosyne"]
                with patch("multi_memory.cli.create_adapter") as mock_create:
                    mock_adapter = MagicMock()
                    mock_adapter.is_available.return_value = True
                    mock_create.return_value = mock_adapter
                    # Should not raise
                    _cmd_validate(args)

    def test_validate_unavailable_backend(self):
        """Validate reports unavailable backends."""
        args = MagicMock()
        args.fix = False

        with patch("multi_memory.cli.load_config") as mock_load:
            mock_load.return_value = {"memory": {"multi": {"backends": ["mnemosyne"]}}}
            with patch("multi_memory.cli.get_enabled_backends") as mock_get:
                mock_get.return_value = ["mnemosyne"]
                with patch("multi_memory.cli.create_adapter") as mock_create:
                    mock_adapter = MagicMock()
                    mock_adapter.is_available.return_value = False
                    mock_create.return_value = mock_adapter
                    # Should report issue
                    _cmd_validate(args)

    def test_validate_adapter_creation_failure(self):
        """Validate handles adapter creation failures."""
        args = MagicMock()
        args.fix = False

        with patch("multi_memory.cli.load_config") as mock_load:
            mock_load.return_value = {"memory": {"multi": {"backends": ["mnemosyne"]}}}
            with patch("multi_memory.cli.get_enabled_backends") as mock_get:
                mock_get.return_value = ["mnemosyne"]
                with patch("multi_memory.cli.create_adapter") as mock_create:
                    mock_create.return_value = None
                    # Should report issue
                    _cmd_validate(args)

    def test_validate_with_fix_flag(self):
        """Validate with --fix flag attempts fixes."""
        args = MagicMock()
        args.fix = True

        with patch("multi_memory.cli.load_config") as mock_load:
            mock_load.return_value = {"memory": {"multi": {"backends": ["mnemosyne"]}}}
            with patch("multi_memory.cli.get_enabled_backends") as mock_get:
                mock_get.return_value = ["mnemosyne"]
                with patch("multi_memory.cli.create_adapter") as mock_create:
                    mock_adapter = MagicMock()
                    mock_adapter.is_available.return_value = False
                    mock_create.return_value = mock_adapter
                    # Should attempt fix
                    _cmd_validate(args)

    def test_validate_invalid_config(self):
        """Validate handles invalid config gracefully."""
        args = MagicMock()
        args.fix = False

        with patch("multi_memory.cli.load_config") as mock_load:
            mock_load.return_value = {"memory": "invalid"}
            # Should handle gracefully
            _cmd_validate(args)

    def test_validate_multiple_backends(self):
        """Validate can check multiple backends."""
        args = MagicMock()
        args.fix = False

        with patch("multi_memory.cli.load_config") as mock_load:
            mock_load.return_value = {
                "memory": {"multi": {"backends": ["mnemosyne", "mem0"]}}
            }
            with patch("multi_memory.cli.get_enabled_backends") as mock_get:
                mock_get.return_value = ["mnemosyne", "mem0"]
                with patch("multi_memory.cli.create_adapter") as mock_create:
                    mock_adapter = MagicMock()
                    mock_adapter.is_available.return_value = True
                    mock_create.return_value = mock_adapter
                    # Should validate both
                    _cmd_validate(args)
                    assert mock_create.call_count == 2
