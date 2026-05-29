"""Tests for multi_memory.budget (ToolBudgetWarning) and validate (NamespaceValidator)."""
from __future__ import annotations

import logging

import pytest

from multi_memory.budget import DEFAULT_THRESHOLD, ToolBudgetWarning
from multi_memory.validate import NamespaceValidator


class TestToolBudgetWarning:
    """ToolBudgetWarning: threshold check + prefix breakdown logging."""

    def test_default_threshold(self):
        tbw = ToolBudgetWarning()
        assert tbw.threshold == DEFAULT_THRESHOLD

    def test_custom_threshold(self):
        tbw = ToolBudgetWarning(threshold=5)
        assert tbw.threshold == 5

    def test_below_threshold_no_warning(self, caplog):
        tbw = ToolBudgetWarning(threshold=10)
        schemas = [{"name": f"tool_{i}"} for i in range(5)]
        with caplog.at_level(logging.WARNING):
            tbw.check(schemas)
        assert len(caplog.records) == 0

    def test_at_threshold_no_warning(self, caplog):
        tbw = ToolBudgetWarning(threshold=5)
        schemas = [{"name": f"tool_{i}"} for i in range(5)]
        with caplog.at_level(logging.WARNING):
            tbw.check(schemas)
        assert len(caplog.records) == 0

    def test_above_threshold_logs_warning(self, caplog):
        tbw = ToolBudgetWarning(threshold=3)
        schemas = [{"name": f"tool_{i}"} for i in range(5)]
        with caplog.at_level(logging.WARNING, logger="multi_memory.budget"):
            tbw.check(schemas)
        assert len(caplog.records) == 1
        msg = caplog.records[0].getMessage()
        assert "ToolBudgetWarning" in msg
        assert "5 schemas" in msg
        assert "exceeds threshold 3" in msg

    def test_prefix_breakdown_in_warning(self, caplog):
        """Warning includes breakdown by prefix (text before first _)."""
        tbw = ToolBudgetWarning(threshold=2)
        schemas = [
            {"name": "mem0_search"},
            {"name": "mem0_add"},
            {"name": "holographic_query"},
            {"name": "holographic_store"},
            {"name": "no_prefix"},
        ]
        with caplog.at_level(logging.WARNING, logger="multi_memory.budget"):
            tbw.check(schemas)
        assert len(caplog.records) == 1
        msg = caplog.records[0].getMessage()
        assert "mem0=2" in msg
        assert "holographic=2" in msg
        assert "no" in msg  # prefix of "no_prefix" is "no"

    def test_empty_schemas_no_warning(self, caplog):
        tbw = ToolBudgetWarning(threshold=5)
        with caplog.at_level(logging.WARNING):
            tbw.check([])
        assert len(caplog.records) == 0

    def test_schemas_without_name_key(self, caplog):
        """Schemas missing 'name' use empty string for prefix extraction."""
        tbw = ToolBudgetWarning(threshold=0)
        schemas = [{}, {"name": "test_tool"}]
        with caplog.at_level(logging.WARNING, logger="multi_memory.budget"):
            tbw.check(schemas)
        assert len(caplog.records) == 1
        msg = caplog.records[0].getMessage()
        assert "(no-prefix)=1" in msg
        assert "test=1" in msg

    def test_threshold_property_immutable(self):
        tbw = ToolBudgetWarning(threshold=10)
        assert tbw.threshold == 10
        # property is read-only on the instance
        with pytest.raises(AttributeError):
            tbw.threshold = 5


class TestNamespaceValidator:
    """NamespaceValidator: validates PREFIX attributes on adapter classes."""

    def test_all_subclasses_have_prefix(self):
        """All nine adapter classes should validate cleanly."""
        from multi_memory.adapters import (
            _MnemosyneAdapter,
            _Mem0Adapter,
            _HolographicAdapter,
            _HonchoAdapter,
            _OpenVikingAdapter,
            _HindsightAdapter,
            _RetainDBAdapter,
            _ByteRoverAdapter,
            _SupermemoryAdapter,
        )

        validator = NamespaceValidator([
            _MnemosyneAdapter,
            _Mem0Adapter,
            _HolographicAdapter,
            _HonchoAdapter,
            _OpenVikingAdapter,
            _HindsightAdapter,
            _RetainDBAdapter,
            _ByteRoverAdapter,
            _SupermemoryAdapter,
        ])
        warnings = validator.validate_all()
        assert warnings == []

    def test_empty_prefix_emits_warning(self, caplog):
        """An adapter class with empty PREFIX generates a warning."""

        class BadAdapter:
            PREFIX = ""
            CONFIG_KEY = "bad"

        validator = NamespaceValidator([BadAdapter])
        with caplog.at_level(logging.WARNING, logger="multi_memory.validate"):
            warnings = validator.validate_all()
        assert len(warnings) == 1
        assert "empty PREFIX" in warnings[0]
        assert "BadAdapter" in warnings[0]

    def test_missing_prefix_attribute_emits_warning(self, caplog):
        """An adapter class without PREFIX generates a warning."""

        class MissingAdapter:
            CONFIG_KEY = "missing"

        validator = NamespaceValidator([MissingAdapter])
        with caplog.at_level(logging.WARNING, logger="multi_memory.validate"):
            warnings = validator.validate_all()
        assert len(warnings) == 1
        assert "empty PREFIX" in warnings[0]

    def test_whitespace_only_prefix_emits_warning(self, caplog):
        """Whitespace-only PREFIX is treated as empty."""

        class SpaceAdapter:
            PREFIX = "   "
            CONFIG_KEY = "space"

        validator = NamespaceValidator([SpaceAdapter])
        with caplog.at_level(logging.WARNING, logger="multi_memory.validate"):
            warnings = validator.validate_all()
        assert len(warnings) == 1
        assert "empty PREFIX" in warnings[0]

    def test_mixed_valid_and_invalid(self, caplog):
        """Only invalid adapters should produce warnings."""

        class GoodAdapter:
            PREFIX = "good"
            CONFIG_KEY = "good"

        class BadAdapter:
            PREFIX = ""
            CONFIG_KEY = "bad"

        validator = NamespaceValidator([GoodAdapter, BadAdapter])
        with caplog.at_level(logging.WARNING, logger="multi_memory.validate"):
            warnings = validator.validate_all()
        assert len(warnings) == 1
        assert "BadAdapter" in warnings[0]
        assert "good" not in warnings[0]

    def test_static_method_validate_prefix(self):
        """validate_prefix static method works independently."""
        assert NamespaceValidator.validate_prefix("mem0", name="test") is None
        result = NamespaceValidator.validate_prefix("", name="empty")
        assert result is not None
        assert "empty PREFIX" in result
        assert "empty" in result

    def test_static_method_none_prefix(self):
        result = NamespaceValidator.validate_prefix(None, name="none_pref")
        assert result is not None
        assert "empty PREFIX" in result

    def test_static_method_returns_none_for_valid(self):
        result = NamespaceValidator.validate_prefix("mnemosyne")
        assert result is None

    def test_static_method_whitespace(self):
        result = NamespaceValidator.validate_prefix("  ", name="whitespace")
        assert result is not None
