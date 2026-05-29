#!/usr/bin/env python3
"""Per-backend health check for multi-memory plugin.

Usage:
    ./scripts/health_check.py                 # check all backends
    ./scripts/health_check.py mnemosyne       # check specific backend
    ./scripts/health_check.py --json          # machine-readable JSON output
    ./scripts/health_check.py --verbose       # verbose diagnostics

Exits 0 if all requested backends are OK, 1 if any are unhealthy,
2 if the plugin itself cannot be imported.
"""

from __future__ import annotations

import argparse
import importlib
import json
import logging
import os
import sys
import traceback
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


# ── Backend definitions ──────────────────────────────────────

BackendDef = dict[str, Any]

BACKENDS: dict[str, BackendDef] = {
    "mnemosyne": {
        "module": "mnemosyne",
        "class": "MemoryProvider",
        "pip": "plugin (github.com/AxDSan/mnemosyne)",
        "env_vars": [],
        "config_key": "mnemosyne",
        "use_plugin_loader": True,
    },
    "holographic": {
        "module": "plugins.memory.holographic",
        "class": "HolographicMemoryProvider",
        "pip": "stdlib-only",
        "env_vars": [],
        "config_key": "holographic",
    },
    "mem0": {
        "module": "plugins.memory.mem0",
        "class": "Mem0MemoryProvider",
        "pip": "mem0ai>=0.1",
        "env_vars": ["MEM0_API_KEY"],
        "config_key": "mem0",
    },
    "honcho": {
        "module": "plugins.memory.honcho",
        "class": "HonchoMemoryProvider",
        "pip": "honcho-ai",
        "env_vars": ["HONCHO_API_KEY", "HONCHO_APP_ID"],
        "config_key": "honcho",
    },
    "openviking": {
        "module": "plugins.memory.openviking",
        "class": "OpenVikingMemoryProvider",
        "pip": "openviking",
        "env_vars": ["OPENVIKING_ENDPOINT"],
        "config_key": "openviking",
    },
    "hindsight": {
        "module": "plugins.memory.hindsight",
        "class": "HindsightMemoryProvider",
        "pip": "hindsight-client",
        "env_vars": ["HINDSIGHT_API_KEY"],
        "config_key": "hindsight",
    },
    "retaindb": {
        "module": "plugins.memory.retaindb",
        "class": "RetainDBMemoryProvider",
        "pip": "retaindb",
        "env_vars": ["RETAINDB_API_KEY"],
        "config_key": "retaindb",
    },
    "byterover": {
        "module": "plugins.memory.byterover",
        "class": "ByteRoverMemoryProvider",
        "pip": "byterover-cli (npm install -g byterover-cli)",
        "env_vars": [],
        "config_key": "byterover",
    },
    "supermemory": {
        "module": "plugins.memory.supermemory",
        "class": "SupermemoryMemoryProvider",
        "pip": "supermemory",
        "env_vars": ["SUPERMEMORY_API_KEY"],
        "config_key": "supermemory",
    },
}


# ── Check helpers ────────────────────────────────────────────

def _try_import(module: str, cls_name: str) -> type | None:
    """Import a class, return None if unavailable."""
    try:
        from importlib.util import find_spec
        if find_spec(module.split(".")[0]) is None:
            return None
        mod = importlib.import_module(module)
        return getattr(mod, cls_name, None)
    except Exception:
        return None


def _env_status(env_vars: list[str]) -> tuple[bool, str]:
    """Check required env vars. Returns (ok, detail)."""
    missing = [v for v in env_vars if not os.environ.get(v)]
    # Also check mem0.json for MEM0_API_KEY
    if "MEM0_API_KEY" in missing:
        try:
            hermes_home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
            mem0_json = hermes_home / "mem0.json"
            if mem0_json.exists():
                import json as _json
                cfg = _json.loads(mem0_json.read_text())
                if cfg.get("api_key"):
                    missing.remove("MEM0_API_KEY")
        except Exception:
            pass
    if not missing:
        return (True, "all set")
    return (False, f"missing: {', '.join(missing)}")


def _init_status(backend_name: str, cls: type) -> tuple[bool, str]:
    """Try instantiating the backend provider. Returns (ok, detail)."""
    try:
        inst = cls()
        available = inst.is_available() if hasattr(inst, "is_available") else True
        name = inst.name if hasattr(inst, "name") else backend_name
        return (True, f"instantiated, name={name!r}, available={available}")
    except Exception as exc:
        return (False, f"init failed: {exc}")


# ── Main ─────────────────────────────────────────────────────

def check_backend(name: str, verbose: bool = False) -> BackendDef:
    """Run all checks for a single backend. Returns enriched def dict."""
    info = BACKENDS.get(name)
    if info is None:
        return {"name": name, "status": "unknown", "error": f"no such backend: {name}"}

    result = dict(info)  # copy
    result["name"] = name
    result["status"] = "pending"

    # 1. Module import — special handling for plugin-loader backends
    if info.get("use_plugin_loader"):
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
            from plugins.memory import load_memory_provider
            provider = load_memory_provider(name)
            cls = type(provider) if provider else None
        except Exception:
            cls = _try_import(info["module"], info["class"])
    else:
        cls = _try_import(info["module"], info["class"])
    if cls is None:
        result["status"] = "unavailable"
        result["error"] = f"module '{info['module']}' not installed"
        result["pip_hint"] = info["pip"]
        return result
    result["module_imported"] = True

    # 2. Env vars
    env_ok, env_detail = _env_status(info["env_vars"])
    result["env"] = {"ok": env_ok, "detail": env_detail}

    # 3. Instantiation
    if cls is not None:
        init_ok, init_detail = _init_status(name, cls)
        result["init"] = {"ok": init_ok, "detail": init_detail}

    result["status"] = "ok" if (env_ok and result.get("init", {}).get("ok", True)) else "degraded"
    return result


def report(result: BackendDef, verbose: bool, json_output: bool) -> None:
    """Print a single backend's health report."""
    name = result["name"]
    status = result["status"]

    if json_output:
        return  # collected below

    if status == "ok":
        symbol = "\033[32m✓\033[0m"
    elif status == "degraded":
        symbol = "\033[33m~\033[0m"
    elif status == "unknown":
        symbol = "\033[35m?\033[0m"
    else:
        symbol = "\033[31m✘\033[0m"

    line = f"{symbol} {name}  —  {status}"
    if result.get("error"):
        line += f"  ({result['error']})"
    if result.get("pip_hint") and result["status"] == "unavailable":
        line += f"\n      Install: {result['pip_hint']}"
    print(line)

    if verbose and result.get("env"):
        e = result["env"]
        print(f"      env: {e['detail']}")
    if verbose and result.get("init"):
        i = result["init"]
        print(f"      init: {i['detail']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="multi-memory plugin health check")
    parser.add_argument("backends", nargs="*", help="Backend(s) to check (default: all)")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose diagnostics")
    args = parser.parse_args()

    names = args.backends or list(BACKENDS.keys())
    results = []
    any_fail = False

    if not args.json:
        print(f"\033[36m➜\033[0m multi-memory health check ({len(names)} backend(s))\n")

    for name in names:
        if name not in BACKENDS:
            result = {"name": name, "status": "unknown", "error": f"no such backend: {name}"}
            results.append(result)
            if not args.json:
                report(result, verbose=args.verbose, json_output=False)
            any_fail = True
            continue
        else:
            result = check_backend(name, verbose=args.verbose)
            if result["status"] != "ok":
                any_fail = True
        results.append(result)
        if not args.json:
            report(result, verbose=args.verbose, json_output=False)

    if args.json:
        print(json.dumps(results, indent=2, default=str))

    return 1 if any_fail else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:
        print(f"\033[31m✘\033[0m health check crashed: {exc}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(2)
