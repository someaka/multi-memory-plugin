"""Config helpers for loading enabled backends from ~/.hermes/config.yaml.

Supports both config shapes:

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
"""
from __future__ import annotations

import os
from typing import Any

import yaml


_HERMES_HOME = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
_CONFIG_PATH = os.path.join(_HERMES_HOME, "config.yaml")


def load_multi_config() -> dict[str, Any]:
    try:
        with open(_CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}


def get_enabled_backends(config: dict | None = None) -> list[str]:
    """Return list of config keys that are enabled in multi.backends."""
    cfg = config or load_multi_config()
    backends = (cfg.get("multi") or {}).get("backends", {})
    return [k for k, v in backends.items() if v]
