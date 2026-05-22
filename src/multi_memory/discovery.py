"""Backend discovery — report which backends are installable on this system.

The ``discover_backends()`` function checks each of the four supported
backends and returns a list of backend descriptors, each with an
``installed`` boolean and module path.
"""

from __future__ import annotations

from importlib.util import find_spec

# Each entry: (config_key, module_path, label)
_BACKEND_REGISTRY: list[tuple[str, str, str]] = [
    ("mnemosyne",   "mnemosyne",                 "Mnemosyne (stdlib)"),
    ("mem0",        "plugins.memory.mem0",       "Mem0"),
    ("holographic", "plugins.memory.holographic", "Holographic (stdlib)"),
    ("honcho",      "plugins.memory.honcho",     "Honcho"),
]


def discover_backends() -> list[dict[str, str | bool]]:
    """Probe all four known backends and report installation status.

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
        installed = find_spec(module_path) is not None
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
