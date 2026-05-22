"""Namespace validation for sub-provider adapters.

Ensures that every ``_SubProviderAdapter`` subclass has a non-empty
``PREFIX`` class attribute so that tool names are properly namespaced
and collisions are avoided.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class NamespaceValidator:
    """Check that adapter classes carry a non-empty ``PREFIX``.

    Parameters
    ----------
    adapter_classes : list[type]
        List of ``_SubProviderAdapter`` subclasses to validate.
    """

    def __init__(self, adapter_classes: list[type]) -> None:
        self._classes = adapter_classes

    def validate_all(self) -> list[str]:
        """Run validation over every registered adapter class.

        Returns
        -------
        list[str]
            Warning messages for each adapter with an empty or missing prefix.
        """
        warnings: list[str] = []
        for cls in self._classes:
            prefix = getattr(cls, "PREFIX", "")
            name = getattr(cls, "CONFIG_KEY", cls.__name__)
            if not prefix or not prefix.strip():
                msg = (
                    f"[multi-memory] NamespaceValidator: {cls.__name__} "
                    f"(CONFIG_KEY={name!r}) has empty PREFIX — "
                    f"tool names will collide across backends"
                )
                logger.warning(msg)
                warnings.append(msg)
            else:
                logger.debug(
                    "[multi-memory] NamespaceValidator: %s PREFIX=%r OK",
                    cls.__name__,
                    prefix,
                )
        return warnings

    @staticmethod
    def validate_prefix(prefix: str, name: str = "adapter") -> str | None:
        """Validate a single prefix string. Returns warning or *None*."""
        if not prefix or not prefix.strip():
            return (
                f"[multi-memory] NamespaceValidator: {name} "
                f"has empty PREFIX — tool names will collide"
            )
        return None
