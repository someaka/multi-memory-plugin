"""CLI commands for the multi-memory plugin.

Registers ``hermes multi`` subcommands for managing active memory backends.

Commands:
    hermes multi status     Show active backends and health
    hermes multi list       List all available backends (installed vs not)
    hermes multi add <name> Add a backend to the active config
    hermes multi remove <name>  Remove a backend from the active config
"""

from __future__ import annotations

import argparse
import json
import logging

from multi_memory import _is_disabled

logger = logging.getLogger(__name__)

try:
    from hermes_cli.config import load_config, save_config
except ImportError:
    # Standalone testing: stubs
    def load_config() -> dict:  # type: ignore[misc]
        return {}

    def save_config(config: dict) -> None:  # type: ignore[misc]
        pass


def register_cli(subparser: argparse.ArgumentParser) -> None:
    """Build the ``hermes multi`` argparse subcommand tree.

    Called by the plugin CLI registration system during argparse setup.
    The *subparser* is the parser for ``hermes multi``.
    """
    subs = subparser.add_subparsers(dest="multi_command")

    # hermes multi status
    status_parser = subs.add_parser(
        "status",
        help="Show active backends and health status",
    )
    status_parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Machine-readable JSON output",
    )

    # hermes multi list
    list_parser = subs.add_parser(
        "list",
        help="List all known backends (installed and available)",
    )
    list_parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Machine-readable JSON output",
    )

    # hermes multi add <backend>
    add_parser = subs.add_parser(
        "add",
        help="Add a memory backend to the active config",
    )
    add_parser.add_argument(
        "backend",
        help="Backend name (e.g. mnemosyne, holographic, mem0)",
    )

    # hermes multi remove <backend>
    remove_parser = subs.add_parser(
        "remove",
        help="Remove a memory backend from the active config",
    )
    remove_parser.add_argument(
        "backend",
        help="Backend name to remove",
    )


def multi_command(args: argparse.Namespace) -> None:
    """Handler for ``hermes multi`` subcommands."""
    sub = getattr(args, "multi_command", None)

    if sub == "status":
        _cmd_status(args)
    elif sub == "list":
        _cmd_list(args)
    elif sub == "add":
        _cmd_add(args)
    elif sub == "remove":
        _cmd_remove(args)
    else:
        # No subcommand — show help
        print("\n  Usage: hermes multi {status|list|add|remove}\n")
        print("  Manage multi-memory backends.\n")
        print("  Commands:")
        print("    status        Show active backends and health")
        print("    list          List all known backends")
        print("    add <name>    Add a backend to config")
        print("    remove <name> Remove a backend from config\n")


def _get_active_backends(memory_cfg: dict) -> list[str]:
    """Extract active backend names from memory config.

    Reads from ``multi.backends`` dict (canonical) with fallback
    to ``providers`` list for backward compatibility.
    """
    multi_cfg = memory_cfg.get("multi", {})
    backends_dict = multi_cfg.get("backends", {})
    providers_list = memory_cfg.get("providers", [])

    if backends_dict:
        return [k for k, v in backends_dict.items() if not _is_disabled(v)]
    if providers_list:
        return [p for p in providers_list if p]
    return []


ALL_BACKENDS: dict[str, str] = {
    "mnemosyne": "Local SQLite + vector recall",
    "holographic": "SQLite fact store, FTS5, HRR compositional algebra",
    "mem0": "Cloud semantic search with auto-extraction",
    "honcho": "Hosted cross-session user modeling",
    "openviking": "Context database with filesystem-style hierarchy",
    "hindsight": "Knowledge graph with entity resolution",
    "retaindb": "Cloud hybrid search with delta compression",
    "byterover": "CLI-first local knowledge tree",
    "supermemory": "Semantic long-term graph memory",
}


def _cmd_status(args: argparse.Namespace) -> None:
    """Show active backends and their health."""
    config = load_config()
    memory_cfg = config.get("memory", {})
    active = _get_active_backends(memory_cfg)
    multi_cfg = memory_cfg.get("multi", {})
    backends_dict = multi_cfg.get("backends", {})

    json_out = getattr(args, "json_output", False)

    # Check installation status for each backend
    backend_info = {}
    try:
        from multi_memory.discovery import discover_backends  # noqa: PLC0415

        for b in discover_backends():
            backend_info[b["config_key"]] = b.get("installed", False)
    except Exception as exc:
        logger.debug("[multi] backend discovery failed: %s", exc)

    if json_out:
        print(
            json.dumps(
                {
                    "provider": "multi",
                    "active_backends": active,
                    "config_format": "backends" if backends_dict else "providers",
                    "installed": {k: v for k, v in backend_info.items() if k in active},
                },
                indent=2,
            )
        )
        return

    print(f"\n  Multi-Memory Provider — {len(active)} active backend(s)")
    print(f"  Config format: {'backends' if backends_dict else 'providers list'}")
    print()

    if not active:
        print("  No backends configured. Use 'hermes multi add <name>' to add one.\n")
        return

    # Header
    print(f"    {'Backend':15s} {'Installed':12s} {'Description'}")
    print(f"    {'─' * 15} {'─' * 12} {'─' * 40}")

    for name in active:
        installed = backend_info.get(name)
        if installed is True:
            status = "✓ installed"
            marker = "→"
        elif installed is False:
            status = "✗ missing"
            marker = "!"
        else:
            status = "? unknown"
            marker = " "
        desc = ALL_BACKENDS.get(name, "")
        print(f"  {marker} {name:15s} {status:12s} {desc}")

    print()


def _cmd_list(args: argparse.Namespace) -> None:
    """List all known backends — installed and available."""
    json_out = getattr(args, "json_output", False)

    config = load_config()
    memory_cfg = config.get("memory", {})
    active_set = set(_get_active_backends(memory_cfg))

    if json_out:
        rows = []
        for name, desc in ALL_BACKENDS.items():
            rows.append(
                {
                    "name": name,
                    "description": desc,
                    "active": name in active_set,
                }
            )
        print(json.dumps(rows, indent=2))
        return

    print("\n  Available memory backends:\n")
    print(f"    {'Name':15s} {'Status':12s} {'Description'}")
    print(f"    {'─' * 15} {'─' * 12} {'─' * 40}")

    for name, desc in ALL_BACKENDS.items():
        is_active = name in active_set

        status = "[active]" if is_active else ""
        marker = "→" if is_active else " "
        print(f"  {marker} {name:15s} {status:12s} {desc}")

    print("\n  Use 'hermes multi add <name>' to activate a backend.\n")


def _cmd_add(args: argparse.Namespace) -> None:
    """Add a backend to the active config."""
    backend = getattr(args, "backend", "").strip()
    if not backend:
        print("\n  Usage: hermes multi add <backend>\n")
        return

    # Validate backend name against known backends
    if backend not in ALL_BACKENDS:
        known = ", ".join(sorted(ALL_BACKENDS.keys()))
        print(f"\n  Unknown backend '{backend}'.")
        print(f"  Known backends: {known}\n")
        return

    config = load_config()
    memory_cfg = config.setdefault("memory", {})
    multi_cfg = memory_cfg.setdefault("multi", {})
    backends_dict = multi_cfg.setdefault("backends", {})

    if backend in backends_dict and not _is_disabled(backends_dict[backend]):
        print(f"\n  '{backend}' is already active.\n")
        return

    backends_dict[backend] = {}

    if not memory_cfg.get("provider") or memory_cfg["provider"] != "multi":
        memory_cfg["provider"] = "multi"

    save_config(config)
    print(f"\n  ✓ Added '{backend}' to active backends.")
    print("  Restart Hermes to activate.\n")


def _cmd_remove(args: argparse.Namespace) -> None:
    """Remove a backend from the active config."""
    backend = getattr(args, "backend", "").strip()
    if not backend:
        print("\n  Usage: hermes multi remove <backend>\n")
        return

    config = load_config()
    memory_cfg = config.get("memory", {})
    if not memory_cfg:
        print("\n  No memory config found.\n")
        return

    found = False

    multi_cfg = memory_cfg.get("multi", {})
    backends_dict = multi_cfg.get("backends", {})
    if backend in backends_dict:
        del backends_dict[backend]
        found = True

    providers_list = memory_cfg.get("providers", [])
    if backend in providers_list:
        providers_list.remove(backend)

    if not found:
        print(f"\n  '{backend}' is not in the active config.\n")
        return

    save_config(config)

    remaining = _get_active_backends(memory_cfg)
    if remaining:
        print(f"\n  ✓ Removed '{backend}'. Active: {', '.join(remaining)}\n")
    else:
        print(f"\n  ✓ Removed '{backend}'. No backends active.")
        print("  Use 'hermes multi add <name>' to add one.\n")
