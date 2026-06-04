"""Config loading for the multi-memory plugin.

Reads ``~/.hermes/config.yaml`` and extracts the multi-memory section.
Supports both ``memory.multi.backends`` (dict) and ``memory.providers``
(list) formats.

Paths are computed lazily to survive profile switches.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import yaml

from multi_memory import _is_disabled

logger = logging.getLogger(__name__)


def _get_hermes_home() -> str:
    """Return HERMES_HOME — computed lazily to survive profile switches."""
    return os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))


def _get_config_path() -> str:
    """Return config.yaml path — computed lazily."""
    return os.path.join(_get_hermes_home(), "config.yaml")


def load_multi_config() -> dict[str, Any]:
    """Load the multi-memory section from config.yaml.

    Returns the raw dict under ``memory`` (or ``{}`` on failure).
    """
    cfg_path = _get_config_path()
    try:
        with open(cfg_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.debug("[multi-memory] config not found at %s", cfg_path)
        return {}
    except (PermissionError, IsADirectoryError, yaml.YAMLError) as exc:
        logger.warning("[multi-memory] failed to read config at %s: %s", cfg_path, exc)
        return {}
    except Exception as exc:
        logger.warning("[multi-memory] unexpected error reading config: %s", exc)
        return {}

    if not isinstance(cfg, dict):
        return {}

    memory_cfg = cfg.get("memory")
    if not isinstance(memory_cfg, dict):
        return {}

    return memory_cfg


def get_enabled_backends(config: dict | None = None) -> list[str]:
    """Return a list of enabled backend names.

    Precedence: ``multi.backends`` > ``providers`` list > ``provider`` string.
    Accepts the ``memory`` section (as returned by ``load_multi_config()``).
    """
    if config is None:
        config = load_multi_config()

    if not isinstance(config, dict):
        return []

    # Dict format takes precedence
    multi_cfg = config.get("multi")
    if isinstance(multi_cfg, dict):
        backends = multi_cfg.get("backends")
        if isinstance(backends, dict) and backends:
            return [
                name for name, enabled in backends.items()
                if not _is_disabled(enabled)
            ]

    # List format
    providers = config.get("providers")
    if isinstance(providers, list) and providers:
        return [p for p in providers if p]

    # Legacy single-string format
    single = config.get("provider", "")
    if single and single != "multi":
        return [single]

    return []
