"""Backend discovery — report which backends are installable on this system.

The ``discover_backends()`` function checks each of the supported
backends and returns a list of backend descriptors, each with an
``installed`` boolean and module path.
"""

from __future__ import annotations

from importlib.util import find_spec
from pathlib import Path

from multi_memory.config import _get_hermes_home

# Each entry: (config_key, module_path, label)
_BACKEND_REGISTRY: list[tuple[str, str, str]] = [
    ("mnemosyne", "mnemosyne", "Mnemosyne (plugin)"),
    ("mem0", "plugins.memory.mem0", "Mem0"),
    ("holographic", "plugins.memory.holographic", "Holographic (stdlib)"),
    ("honcho", "plugins.memory.honcho", "Honcho"),
    ("openviking", "plugins.memory.openviking", "OpenViking"),
    ("hindsight", "plugins.memory.hindsight", "Hindsight"),
    ("retaindb", "plugins.memory.retaindb", "RetainDB"),
    ("byterover", "plugins.memory.byterover", "ByteRover"),
    ("supermemory", "plugins.memory.supermemory", "Supermemory"),
]

__all__ = ["discover_backends", "installed_backends"]


def _is_mnemosyne_plugin_installed() -> bool:
    """Check if the Mnemosyne user-installed plugin exists."""
    hermes_home = _get_hermes_home()
    plugin_dir = Path(hermes_home) / "plugins" / "mnemosyne"
    return plugin_dir.is_dir() and (plugin_dir / "__init__.py").exists()


def discover_backends() -> list[dict[str, str | bool]]:
    """Probe all known backends and report installation status.

    Returns
    -------
    list[dict]
        One dict per backend with keys:
        - ``config_key``  — short name used in config.yaml
        - ``module``      — dotted module path
        - ``label``       — human-readable label
        - ``installed``   — ``True`` if the module can be imported
    """
    results: list[dict[str, str | bool]] = []
    for config_key, module_path, label in _BACKEND_REGISTRY:
        if config_key == "mnemosyne":
            # Mnemosyne is a user-installed plugin, not a pip package
            installed = _is_mnemosyne_plugin_installed()
        else:
            try:
                installed = find_spec(module_path) is not None
            except (ModuleNotFoundError, ValueError):
                installed = False
        results.append(
            {
                "config_key": config_key,
                "module": module_path,
                "label": label,
                "installed": installed,
            }
        )
    return results


def installed_backends() -> list[str]:
    """Return config_key strings for backends that are currently installed."""
    return [b["config_key"] for b in discover_backends() if b["installed"]]  # type: ignore[literal-required]
