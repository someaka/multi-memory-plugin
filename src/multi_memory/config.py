"""Config helpers for loading enabled backends from ~/.hermes/config.yaml.

Supports three config shapes:

1. PLAN spec (friendly)::

    memory:
      provider: multi
      multi:
        backends:
          mnemosyne: {}
          mem0: {}

2. INVESTIGATION-C canonical (fork format)::

    memory:
      providers:
        - "mnemosyne"
        - "mem0"

3. Legacy single-provider string (backward compat)::

    memory:
      provider: "mem0"
"""
from __future__ import annotations

import os
from typing import Any

import yaml


_HERMES_HOME = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
_CONFIG_PATH = os.path.join(_HERMES_HOME, "config.yaml")

__all__ = ["load_multi_config", "get_enabled_backends"]


def load_multi_config() -> dict[str, Any]:
    """Load the Hermes config YAML from the default path."""
    try:
        with open(_CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}


def get_enabled_backends(config: dict | None = None) -> list[str]:
    """Return list of enabled backend config keys.

    Reads from ``multi.backends`` dict (PLAN spec), then ``memory.providers``
    list (INVESTIGATION-C canonical), then falls back to legacy
    ``memory.provider`` string.  First non-empty wins.
    """
    cfg = config or load_multi_config()

    # 1. PLAN spec: multi.backends dict
    #    Accept both top-level {"multi": {"backends": ...}} (tests / standalone)
    #    and nested {"memory": {"multi": {"backends": ...}}} (real config.yaml).
    memory_cfg = cfg.get("memory") or {}
    multi_cfg = cfg.get("multi") or memory_cfg.get("multi") or {}
    backends = multi_cfg.get("backends") or {}
    if isinstance(backends, dict) and backends:
        return [k for k, v in backends.items() if v not in (False, None, 0, "0", "false", "False", "no")]

    # 2. INVESTIGATION-C canonical: providers list
    providers = memory_cfg.get("providers") or []
    if isinstance(providers, list) and providers:
        return [p for p in providers if p]

    # 3. Legacy: single provider string
    single = memory_cfg.get("provider") or ""
    if isinstance(single, str) and single and single != "multi":
        return [single]

    return []
