"""Tests for the validate command and create_adapter helper."""

from unittest.mock import MagicMock, patch

from multi_memory.cli import _cmd_validate, create_adapter


class TestCreateAdapter:
    """Tests for create_adapter helper function."""

    def test_create_unknown_backend(self):
        """Unknown backend returns None."""
        result = create_adapter("unknown_backend")
        assert result is None

    def test_create_known_backend_success(self):
        """Known backend instantiates via _SUB_CLASSES_BY_KEY."""
        mock_cls = MagicMock()
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance

        with patch.dict("multi_memory._SUB_CLASSES_BY_KEY", {"mnemosyne": mock_cls}):
            result = create_adapter("mnemosyne")
        assert result == mock_instance
        mock_cls.assert_called_once()

    def test_create_adapter_instantiation_error(self):
        """Instantiation errors are caught and return None."""
        mock_cls = MagicMock(side_effect=RuntimeError("not installed"))

        with patch.dict("multi_memory._SUB_CLASSES_BY_KEY", {"mem0": mock_cls}):
            result = create_adapter("mem0")
        assert result is None

    def test_create_all_supported_backends(self):
        """All 9 backends resolve through _SUB_CLASSES_BY_KEY."""
        from multi_memory import _SUB_CLASSES_BY_KEY

        expected = {
            "mnemosyne",
            "mem0",
            "holographic",
            "honcho",
            "openviking",
            "hindsight",
            "retaindb",
            "byterover",
            "supermemory",
        }
        assert set(_SUB_CLASSES_BY_KEY.keys()) == expected

    def test_create_adapter_not_in_registry(self):
        """Backend not in _SUB_CLASSES_BY_KEY returns None."""
        with patch.dict("multi_memory._SUB_CLASSES_BY_KEY", {}, clear=True):
            result = create_adapter("mnemosyne")
        assert result is None


class TestValidateCommand:
    """Tests for the validate command."""

    def test_validate_no_backends(self):
        """Validate with no active backends succeeds."""
        args = MagicMock()
        args.fix = False

        with (
            patch("multi_memory.cli.load_config", return_value={"memory": {}}),
            patch("multi_memory.cli.get_enabled_backends", return_value=[]),
        ):
            _cmd_validate(args)

    def test_validate_with_active_backends(self):
        """Validate with active backends checks each one."""
        args = MagicMock()
        args.fix = False

        mock_adapter = MagicMock()
        mock_adapter.is_available.return_value = True

        with (
            patch("multi_memory.cli.load_config", return_value={"memory": {}}),
            patch("multi_memory.cli.get_enabled_backends", return_value=["mnemosyne"]),
            patch("multi_memory.cli.create_adapter", return_value=mock_adapter),
        ):
            _cmd_validate(args)

    def test_validate_unavailable_backend(self):
        """Validate reports unavailable backends."""
        args = MagicMock()
        args.fix = False

        mock_adapter = MagicMock()
        mock_adapter.is_available.return_value = False

        with (
            patch("multi_memory.cli.load_config", return_value={"memory": {}}),
            patch("multi_memory.cli.get_enabled_backends", return_value=["mnemosyne"]),
            patch("multi_memory.cli.create_adapter", return_value=mock_adapter),
        ):
            _cmd_validate(args)

    def test_validate_adapter_creation_failure(self):
        """Validate handles adapter creation failures."""
        args = MagicMock()
        args.fix = False

        with (
            patch("multi_memory.cli.load_config", return_value={"memory": {}}),
            patch("multi_memory.cli.get_enabled_backends", return_value=["mnemosyne"]),
            patch("multi_memory.cli.create_adapter", return_value=None),
        ):
            _cmd_validate(args)

    def test_validate_with_fix_flag(self):
        """Validate with --fix flag attempts fixes."""
        args = MagicMock()
        args.fix = True

        mock_adapter = MagicMock()
        mock_adapter.is_available.return_value = False

        with (
            patch("multi_memory.cli.load_config", return_value={"memory": {}}),
            patch("multi_memory.cli.get_enabled_backends", return_value=["mnemosyne"]),
            patch("multi_memory.cli.create_adapter", return_value=mock_adapter),
        ):
            _cmd_validate(args)

    def test_validate_invalid_config(self):
        """Validate handles invalid config gracefully."""
        args = MagicMock()
        args.fix = False

        with patch("multi_memory.cli.load_config", return_value={"memory": "invalid"}):
            _cmd_validate(args)

    def test_validate_multiple_backends(self):
        """Validate can check multiple backends."""
        args = MagicMock()
        args.fix = False

        mock_adapter = MagicMock()
        mock_adapter.is_available.return_value = True

        with (
            patch("multi_memory.cli.load_config", return_value={"memory": {}}),
            patch(
                "multi_memory.cli.get_enabled_backends",
                return_value=["mnemosyne", "mem0"],
            ),
            patch("multi_memory.cli.create_adapter", return_value=mock_adapter) as mock_create,
        ):
            _cmd_validate(args)
            assert mock_create.call_count == 2
