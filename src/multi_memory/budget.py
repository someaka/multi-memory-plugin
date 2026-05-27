"""Tool budget monitor — warns when get_tool_schemas() returns >N schemas.

Usage
-----
    from multi_memory.budget import ToolBudgetWarning

    warning = ToolBudgetWarning(threshold=20)
    schemas = provider.get_tool_schemas()
    warning.check(schemas)   # logs warning if len(schemas) > threshold
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD = 20

__all__ = ["ToolBudgetWarning", "DEFAULT_THRESHOLD"]


class ToolBudgetWarning:
    """Lightweight threshold checker for tool schema counts.

    When ``check()`` is called and the schema count exceeds the threshold,
    a warning is logged with the actual count and the breakdown by prefix.

    Parameters
    ----------
    threshold : int
        Schema count above which a warning is emitted (default 20).
    """

    def __init__(self, threshold: int = DEFAULT_THRESHOLD) -> None:
        self._threshold = threshold

    @property
    def threshold(self) -> int:
        return self._threshold

    def check(self, schemas: list[dict[str, Any]]) -> None:
        """Log a warning if *schemas* exceeds the configured threshold."""
        count = len(schemas)
        if count <= self._threshold:
            return

        # Build a quick breakdown by prefix (text before first ``_``)
        by_prefix: dict[str, int] = {}
        for s in schemas:
            name = s.get("name", "")
            prefix = name.split("_")[0] if "_" in name else "(no-prefix)"
            by_prefix[prefix] = by_prefix.get(prefix, 0) + 1

        prefix_detail = ", ".join(f"{k}={v}" for k, v in sorted(by_prefix.items()))
        logger.warning(
            "[multi-memory] ToolBudgetWarning: %d schemas exceeds threshold %d — %s",
            count,
            self._threshold,
            prefix_detail,
        )
