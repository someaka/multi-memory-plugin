"""CLI commands for the multi-memory plugin.

Registers ``hermes multi`` subcommands for managing active memory backends.

Commands:
    hermes multi status       Show active backends and health
    hermes multi list         List all available backends (installed vs not)
    hermes multi add <name>   Add a backend to the active config
    hermes multi remove <name>  Remove a backend from the active config
    hermes multi setup        Interactive curses-based setup wizard
    hermes multi setup <name> Configure a specific backend interactively
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

from multi_memory import _is_disabled

logger = logging.getLogger(__name__)

# ── Hermes-specific imports (with standalone fallbacks) ──────────────────

try:
    from hermes_cli.config import load_config, save_config
except ImportError:
    def load_config() -> dict:  # type: ignore[misc]
        return {}
    def save_config(config: dict) -> None:  # type: ignore[misc]
        pass

try:
    from hermes_constants import get_hermes_home
except ImportError:
    def get_hermes_home() -> str:
        return os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))

try:
    from hermes_cli.secret_prompt import masked_secret_prompt
except ImportError:
    def masked_secret_prompt(prompt: str) -> str:
        import getpass
        return getpass.getpass(prompt)


# ── Backend registry ──────────────────────────────────────────────────────

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


# ── argparse registration ─────────────────────────────────────────────────

def register_cli(subparser: argparse.ArgumentParser) -> None:
    """Build the ``hermes multi`` argparse subcommand tree."""
    subs = subparser.add_subparsers(dest="multi_command")

    # hermes multi status
    sp = subs.add_parser("status", help="Show active backends and health status")
    sp.add_argument("--json", dest="json_output", action="store_true",
                    help="Machine-readable JSON output")

    # hermes multi list
    sp = subs.add_parser("list", help="List all known backends")
    sp.add_argument("--json", dest="json_output", action="store_true",
                    help="Machine-readable JSON output")

    # hermes multi add <backend>
    sp = subs.add_parser("add", help="Add a memory backend to the active config")
    sp.add_argument("backend", help="Backend name (e.g. mnemosyne, holographic, mem0)")

    # hermes multi remove <backend>
    sp = subs.add_parser("remove", help="Remove a memory backend from the active config")
    sp.add_argument("backend", help="Backend name to remove")

    # hermes multi setup [backend]
    sp = subs.add_parser("setup", help="Interactive setup wizard for memory backends")
    sp.add_argument("backend", nargs="?", help="Backend name to configure directly")


# ── Command router ─────────────────────────────────────────────────────────

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
    elif sub == "setup":
        backend = getattr(args, "backend", None)
        if backend:
            _cmd_setup_backend(backend)
        else:
            _cmd_setup_wizard(args)
    else:
        print("\n  Usage: hermes multi {status|list|add|remove|setup}\n")
        print("  Manage multi-memory backends.\n")
        print("  Commands:")
        print("    status          Show active backends and health")
        print("    list            List all known backends")
        print("    add <name>      Add a backend to config")
        print("    remove <name>   Remove a backend from config")
        print("    setup [name]    Interactive setup wizard\n")


# ── Config helpers ─────────────────────────────────────────────────────────

def _get_active_backends(memory_cfg: dict) -> list[str]:
    """Extract active backend names from memory config."""
    multi_cfg = memory_cfg.get("multi", {})
    backends_dict = multi_cfg.get("backends", {})
    providers_list = memory_cfg.get("providers", [])

    if backends_dict:
        return [k for k, v in backends_dict.items() if not _is_disabled(v)]
    elif providers_list:
        return [p for p in providers_list if p]
    return []


# ── Provider discovery (Hermes plugin system) ──────────────────────────────

def _get_available_backends() -> list[tuple[str, str, Any]]:
    """Discover installed memory backends via the Hermes plugin system.

    Returns list of (name, setup_hint, provider_instance) tuples.
    Falls back to ALL_BACKENDS registry when running standalone.
    """
    try:
        from plugins.memory import discover_memory_providers, load_memory_provider
        raw = discover_memory_providers()
    except Exception:
        raw = []

    if not raw:
        # Standalone: use registry
        results = []
        for name, desc in ALL_BACKENDS.items():
            results.append((name, desc, None))
        return results

    results = []
    for name, _desc, _available in raw:
        try:
            provider = load_memory_provider(name)
            if not provider:
                continue
        except Exception:
            continue

        schema = provider.get_config_schema() if hasattr(provider, "get_config_schema") else []
        has_secrets = any(f.get("secret") for f in schema)
        has_non_secrets = any(not f.get("secret") for f in schema)
        if has_secrets and has_non_secrets:
            setup_hint = "API key / local"
        elif has_secrets:
            setup_hint = "requires API key"
        elif not schema:
            setup_hint = "no setup needed"
        else:
            setup_hint = "local"

        results.append((name, setup_hint, provider))
    return results


# ── Dependency installer ───────────────────────────────────────────────────

def _find_provider_dir(provider_name: str) -> Path | None:
    """Find the plugin directory for a memory provider."""
    try:
        from plugins.memory import find_provider_dir
        return find_provider_dir(provider_name)
    except Exception:
        return None


def _install_dependencies(provider_name: str) -> None:  # noqa: PLR0912,PLR0915
    """Install pip dependencies declared in the provider's plugin.yaml."""
    import shutil

    plugin_dir = _find_provider_dir(provider_name)
    if not plugin_dir:
        return
    yaml_path = plugin_dir / "plugin.yaml"
    if not yaml_path.exists():
        return

    try:
        import yaml
        with open(yaml_path, encoding="utf-8") as f:
            meta = yaml.safe_load(f) or {}
    except Exception:
        return

    pip_deps = meta.get("pip_dependencies", [])
    if not pip_deps:
        return

    import_names = {
        "honcho-ai": "honcho",
        "mem0ai": "mem0",
        "hindsight-client": "hindsight_client",
        "hindsight-all": "hindsight",
    }

    missing = []
    for dep in pip_deps:
        import_name = import_names.get(dep, dep.replace("-", "_").split("[")[0])
        try:
            __import__(import_name)
        except ImportError:
            missing.append(dep)

    if not missing:
        return

    print(f"\n  Installing dependencies: {', '.join(missing)}")

    uv_path = shutil.which("uv")
    if uv_path:
        install_cmd = [uv_path, "pip", "install", "--python", sys.executable, "--quiet"] + missing
        manual_cmd = f"uv pip install --python {sys.executable} {' '.join(missing)}"
    else:
        pip_cmd = shutil.which("pip3") or shutil.which("pip")
        if not pip_cmd:
            print("  ⚠ uv not found — cannot install dependencies")
            print("  Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh")
            print("  Then re-run: hermes multi setup")
            return
        print("  ⚠ uv not found. Falling back to standard pip...")
        install_cmd = [sys.executable, "-m", "pip", "install", "--quiet"] + missing
        manual_cmd = f"{sys.executable} -m pip install {' '.join(missing)}"

    try:
        subprocess.run(install_cmd, check=True, timeout=120, capture_output=True)
        print(f"  ✓ Installed {', '.join(missing)}")
    except subprocess.CalledProcessError as e:
        print(f"  ⚠ Failed to install {', '.join(missing)}")
        stderr = (e.stderr or b"").decode()[:200]
        if stderr:
            print(f"    {stderr}")
        print(f"  Run manually: {manual_cmd}")
    except Exception as e:
        print(f"  ⚠ Install failed: {e}")
        print(f"  Run manually: {manual_cmd}")

    # Show external (non-pip) dependencies
    ext_deps = meta.get("external_dependencies", [])
    for dep in ext_deps:
        dep_name = dep.get("name", "")
        check_cmd = dep.get("check", "")
        install_cmd_str = dep.get("install", "")
        if check_cmd:
            try:
                subprocess.run(
                    shlex.split(check_cmd), check=True, capture_output=True, timeout=5
                )
            except Exception:
                if install_cmd_str:
                    print(f"\n  ⚠ '{dep_name}' not found. Install with:")
                    print(f"    {install_cmd_str}")


# ── Env var manager ────────────────────────────────────────────────────────

def _write_env_vars(env_path: Path, env_writes: dict) -> None:
    """Append or update env vars in .env file, restricting permissions."""
    env_path.parent.mkdir(parents=True, exist_ok=True)

    existing_lines = []
    if env_path.exists():
        existing_lines = env_path.read_text(encoding="utf-8").splitlines()

    updated_keys = set()
    new_lines = []
    for line in existing_lines:
        key_match = line.split("=", 1)[0].strip() if "=" in line else ""
        if key_match in env_writes:
            new_lines.append(f"{key_match}={env_writes[key_match]}")
            updated_keys.add(key_match)
        else:
            new_lines.append(line)

    for key, val in env_writes.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={val}")

    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    try:
        import stat
        env_path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600
    except OSError:
        pass


# ── Interactive picker ─────────────────────────────────────────────────────

def _curses_select(title: str, items: list[tuple[str, str]], default: int = 0) -> int:
    """Interactive single-select with arrow keys (curses-based).

    Falls back to simple numbered terminal picker if curses unavailable.
    """
    try:
        from hermes_cli.curses_ui import curses_radiolist
        display_items = [
            f"{label}  {desc}" if desc else label
            for label, desc in items
        ]
        return curses_radiolist(title, display_items, selected=default, cancel_returns=default)
    except ImportError:
        # Simple terminal fallback
        print(f"\n  {title}\n")
        for i, (label, desc) in enumerate(items):
            marker = "→" if i == default else " "
            print(f"  {marker} [{i}] {label}  {desc}")
        print()
        try:
            choice = input(f"  Select [{default}]: ").strip()
            return int(choice) if choice else default
        except (ValueError, EOFError):
            return default


def _curses_checklist(title: str, items: list[str],
                       selected: set[int] | None = None) -> set[int]:
    """Interactive multi-select checklist (curses-based).

    Falls back to simple space-separated terminal picker if curses unavailable.
    """
    try:
        from hermes_cli.curses_ui import curses_checklist
        return curses_checklist(title, items, selected=selected or set())
    except ImportError:
        # Simple terminal fallback
        print(f"\n  {title}\n")
        sel = selected or set(range(len(items)))
        for i, item in enumerate(items):
            marker = "[x]" if i in sel else "[ ]"
            print(f"  {marker} {item}")
        print()
        try:
            inp = input("  Enter numbers to keep (space-separated, blank=all): ").strip()
            if not inp:
                return sel
            return {int(n) for n in inp.split()}
        except (ValueError, EOFError):
            return sel


# ── Interactive setup wizard ───────────────────────────────────────────────

def _cmd_setup_wizard(args: argparse.Namespace) -> None:  # noqa: PLR0912,PLR0915
    """Interactive curses-based memory backend setup wizard."""
    backends = _get_available_backends()

    if not backends:
        print("\n  No memory backend plugins detected.")
        print("  Install a plugin to ~/.hermes/plugins/ and try again.\n")
        return

    config = load_config()
    memory_cfg = config.setdefault("memory", {})

    active = _get_active_backends(memory_cfg)
    if active:
        print(f"\n  Currently active: {', '.join(active)}")
        print("  You can add more backends or change your selection.\n")

    # Build picker items
    items: list[tuple[str, str]] = []
    backend_names: list[str] = []

    remove_idx = -1
    if active:
        items.append(("Remove a backend...", "— deactivate an active backend"))
        remove_idx = 0

    for name, hint, _ in backends:
        items.append((name, f"— {hint}"))
        backend_names.append(name)

    items.append(("Built-in only", "— MEMORY.md / USER.md (default)"))

    # Pre-select first active, or built-in if none
    builtin_idx = len(items) - 1
    pre_selected: set[int] = set()
    for i, name in enumerate(backend_names):
        if name in active:
            pre_selected.add(i)

    if not pre_selected:
        pre_selected = {builtin_idx}

    if remove_idx >= 0:
        default_idx = (min(pre_selected) + 1) if pre_selected else 0
    else:
        default_idx = pre_selected.pop() if len(pre_selected) == 1 else 0

    selected = _curses_select("Memory backend setup", items, default=default_idx)

    # Handle "Remove a backend..."
    if selected == remove_idx and remove_idx >= 0:
        remove_items = list(active)
        if not remove_items:
            print("\n  No active backends to remove.\n")
            return

        keep = _curses_checklist(
            title="Backends to KEEP (uncheck to remove)",
            items=remove_items,
            selected=set(range(len(remove_items))),
        )

        to_remove = [remove_items[i] for i in range(len(remove_items)) if i not in keep]
        if not to_remove:
            print("\n  No changes made.\n")
            return

        for backend_name in to_remove:
            _remove_backend_from_config(backend_name, memory_cfg)

        save_config(config)
        remaining = _get_active_backends(memory_cfg)
        if remaining:
            print(f"\n  ✓ Removed: {', '.join(to_remove)}")
            print(f"  Active backends: {', '.join(remaining)}")
        else:
            print(f"\n  ✓ Removed: {', '.join(to_remove)}")
            print("  Active backends: (none — built-in only)")
        print("  Restart Hermes to activate.\n")
        return

    # Adjust for remove entry offset
    if remove_idx >= 0:
        selected -= 1

    # Built-in only
    if selected >= len(backends) or selected < 0:
        _set_active_backends(memory_cfg, [])
        save_config(config)
        print("\n  ✓ Memory backend: built-in only")
        print("  Saved to config.yaml\n")
        return

    name, _, provider = backends[selected]
    _do_backend_setup(name, provider)
    # Config already saved by _do_backend_setup


def _cmd_setup_backend(backend_name: str) -> None:
    """Configure a specific backend, skipping the picker."""
    backends = _get_available_backends()
    match = None
    for name, hint, provider in backends:
        if name == backend_name:
            match = (name, hint, provider)
            break

    if not match:
        print(f"\n  Backend '{backend_name}' not found.")
        print("  Run 'hermes multi setup' to see available backends.\n")
        return

    name, _, provider = match
    config = load_config()
    config.setdefault("memory", {})

    _do_backend_setup(name, provider)
    # Config already saved by _do_backend_setup


def _do_backend_setup(name: str, provider: Any) -> None:  # noqa: PLR0912,PLR0915
    """Run the full setup flow for a single backend."""
    _install_dependencies(name)

    config = load_config()
    memory_cfg = config.get("memory", {})
    if not isinstance(memory_cfg, dict):
        memory_cfg = {}
        config["memory"] = memory_cfg
    active = _get_active_backends(memory_cfg)

    # Ask add-alongside vs replace
    replace_existing = False
    if active and name not in active:
        print(f"\n  Currently active: {', '.join(active)}")
        choice_items = [
            (f"Add {name} alongside", f"Keep {', '.join(active)} and add {name}"),
            ("Replace all", f"Use {name} only"),
        ]
        choice_idx = _curses_select("  Active backends already configured", choice_items, default=0)
        replace_existing = (choice_idx == 1)

    # If provider has post_setup, delegate
    if provider and hasattr(provider, "post_setup"):
        hermes_home = str(get_hermes_home())
        provider.post_setup(hermes_home, config)
        if replace_existing:
            _set_active_backends(memory_cfg, [name])
            active = [name]
        else:
            active = _get_active_backends(memory_cfg)
            if name not in active:
                active.append(name)
            _set_active_backends(memory_cfg, active)
        print(f"\n  Active backends: {', '.join(active)}")
        print("  Start a new session to activate.\n")
        return

    # Generic schema-based setup
    schema = (
        provider.get_config_schema()
        if provider and hasattr(provider, "get_config_schema")
        else []
    )

    provider_config: dict = memory_cfg.get(name, {})
    if not isinstance(provider_config, dict):
        provider_config = {}

    env_path = Path(get_hermes_home()) / ".env"
    env_writes: dict = {}

    if schema:
        print(f"\n  Configuring {name}:\n")

        for field in schema:
            key = field["key"]
            desc = field.get("description", key)
            default = field.get("default")
            default_from = field.get("default_from")
            if default_from and isinstance(default_from, dict):
                ref_field = default_from.get("field", "")
                ref_map = default_from.get("map", {})
                ref_value = provider_config.get(ref_field, "")
                if ref_value and ref_value in ref_map:
                    default = ref_map[ref_value]
            is_secret = field.get("secret", False)
            choices = field.get("choices")
            env_var = field.get("env_var")
            url = field.get("url")

            when = field.get("when")
            if (
                when
                and isinstance(when, dict)
                and not all(provider_config.get(k) == v for k, v in when.items())
            ):
                continue

            if choices and not is_secret:
                choice_items = [(c, "") for c in choices]
                current = provider_config.get(key, default)
                current_idx = 0
                if current and current in choices:
                    current_idx = choices.index(current)
                sel = _curses_select(f"  {desc}", choice_items, default=current_idx)
                provider_config[key] = choices[sel]
            elif is_secret:
                existing = os.environ.get(env_var, "") if env_var else ""
                if existing:
                    masked = f"...{existing[-4:]}" if len(existing) > 4 else "set"  # noqa: PLR2004
                    val = _prompt(f"{desc} (current: {masked}, blank to keep)", secret=True)
                else:
                    if url:
                        print(f"  Get yours at {url}")
                    val = _prompt(desc, secret=True)
                if val and env_var:
                    env_writes[env_var] = val
            else:
                current = provider_config.get(key)
                effective_default = current or default
                val = _prompt(desc, default=str(effective_default) if effective_default else None)
                if val:
                    provider_config[key] = val
                    if env_var and env_var not in env_writes:
                        env_writes[env_var] = val

    # Store provider config
    if provider_config:
        memory_cfg[name] = provider_config
        if provider and hasattr(provider, "save_config"):
            try:
                provider.save_config(provider_config, str(get_hermes_home()))
            except Exception as e:
                print(f"  Failed to write provider config: {e}")

    # Update active backends
    if replace_existing:
        _set_active_backends(memory_cfg, [name])
        active = [name]
    else:
        active = _get_active_backends(memory_cfg)
        if name not in active:
            active.append(name)
        _set_active_backends(memory_cfg, active)

    # Write secrets to .env
    if env_writes:
        _write_env_vars(env_path, env_writes)

    print(f"\n  Backend: {name}")
    print(f"  Active backends: {', '.join(active)}")
    print("  Saved to config.yaml")
    if provider_config:
        print("  Backend config saved")
    if env_writes:
        print("  API keys saved to .env")
    print("\n  Restart Hermes to activate.\n")

    save_config(config)


# ── Prompt helper ──────────────────────────────────────────────────────────

def _prompt(label: str, default: str | None = None, secret: bool = False) -> str:
    """Prompt for a value with optional default and secret masking."""
    suffix = f" [{default}]" if default else ""
    if secret:
        val = masked_secret_prompt(f"  {label}{suffix}: ")
    else:
        sys.stdout.write(f"  {label}{suffix}: ")
        sys.stdout.flush()
        val = sys.stdin.readline().strip()
    return val or (default or "")


# ── Config writers ─────────────────────────────────────────────────────────

def _set_active_backends(memory_cfg: dict, names: list[str]) -> None:
    """Write backend list to both config formats."""
    memory_cfg["providers"] = list(names)
    memory_cfg["provider"] = names[0] if names else ""
    # Also update multi.backends dict
    multi_cfg = memory_cfg.setdefault("multi", {})
    backends = multi_cfg.setdefault("backends", {})
    for name in names:
        if name not in backends:
            backends[name] = {}
    # Remove names no longer active
    for key in list(backends.keys()):
        if key not in names:
            del backends[key]


def _remove_backend_from_config(name: str, memory_cfg: dict) -> None:
    """Remove a backend from both config formats."""
    providers = memory_cfg.get("providers", [])
    if name in providers:
        providers.remove(name)
        memory_cfg["providers"] = providers
        memory_cfg["provider"] = providers[0] if providers else ""

    multi_cfg = memory_cfg.get("multi", {})
    backends = multi_cfg.get("backends", {})
    if name in backends:
        del backends[name]


# ── Status ─────────────────────────────────────────────────────────────────

def _cmd_status(args: argparse.Namespace) -> None:  # noqa: PLR0912,PLR0915
    """Show active backends and their health/config."""
    config = load_config()
    memory_cfg = config.get("memory", {})
    active = _get_active_backends(memory_cfg)
    top_provider = memory_cfg.get("provider", "")
    json_out = getattr(args, "json_output", False)

    if json_out:
        print(json.dumps({
            "provider": top_provider or "built-in",
            "active_backends": active,
            "config_format": (
                "backends" if memory_cfg.get("multi", {}).get("backends")
                else "providers"
            ),
        }, indent=2))
        return

    print("\n  Memory status")
    print("  " + "─" * 40)
    print("  Built-in:     always active")

    if top_provider:
        print(f"  Provider:     {top_provider}")
    elif active:
        print(f"  Providers:    {', '.join(active)}")
    else:
        print("  Provider:     (none — built-in only)")

    # Show top-level provider config if it has sub-config
    if top_provider and top_provider not in active:
        top_config = memory_cfg.get(top_provider, {})
        if top_config and isinstance(top_config, dict):
            print(f"\n    ── {top_provider} ──")
            # Check for format_config_display
            backends_list = _get_available_backends()
            provider_obj = next((p for n, _, p in backends_list if n == top_provider), None)
            if provider_obj and hasattr(provider_obj, "format_config_display"):
                for key, val in provider_obj.format_config_display(top_config):
                    print(f"      {key}: {val}")
            else:
                for key, val in top_config.items():
                    if isinstance(val, dict) and val:
                        items = ", ".join(
                            f"{k}" if v in ({}, True) else f"{k}({v})"
                            for k, v in val.items()
                        )
                        print(f"      {key}: {items}")
                    elif isinstance(val, list):
                        print(f"      {key}: {', '.join(str(v) for v in val)}")
                    else:
                        print(f"      {key}: {val}")

    # Show each active backend
    if active:
        for backend_name in active:
            print(f"\n    ── {backend_name} ──")
            backend_cfg = memory_cfg.get(backend_name, {})
            if isinstance(backend_cfg, dict) and backend_cfg:
                print("    Config:")
                for key, val in backend_cfg.items():
                    if isinstance(val, dict) and val:
                        items = ", ".join(
                            f"{k}" if v in ({}, True) else f"{k}({v})"
                            for k, v in val.items()
                        )
                        print(f"      {key}: {items}")
                    elif isinstance(val, list):
                        print(f"      {key}: {', '.join(str(v) for v in val)}")
                    else:
                        print(f"      {key}: {val}")

            backends_list = _get_available_backends()
            found = any(n == backend_name for n, _, _ in backends_list)
            if found:
                print("    Plugin:       installed ✓")
                for bname, _, bprov in backends_list:
                    if bname == backend_name and bprov:
                        if bprov.is_available():
                            print("    Status:       available ✓")
                        else:
                            print("    Status:       not available ✗")
                            schema = (
                                bprov.get_config_schema()
                                if hasattr(bprov, "get_config_schema")
                                else []
                            )
                            required = [f for f in schema if f.get("env_var")]
                            if required:
                                print("    Missing env vars:")
                                for f in required:
                                    ev = f.get("env_var", "")
                                    url = f.get("url", "")
                                    is_set = bool(os.environ.get(ev))
                                    mark = "✓" if is_set else "✗"
                                    line = f"      {mark} {ev}"
                                    if url and not is_set:
                                        line += f"  → {url}"
                                    print(line)
                        break
            else:
                print("    Plugin:       NOT installed ✗")
                print(f"    Install the '{backend_name}' plugin to ~/.hermes/plugins/")

    # List installed plugins
    backends_list = _get_available_backends()
    if backends_list:
        print("\n  Installed plugins:")
        for bname, hint, _ in backends_list:
            marker = " ← active" if bname in active else ""
            print(f"    • {bname}  ({hint}){marker}")

    print()


# ── List ───────────────────────────────────────────────────────────────────

def _cmd_list(args: argparse.Namespace) -> None:
    """List all known backends — installed and available."""
    json_out = getattr(args, "json_output", False)

    active_set = set(_get_active_backends(load_config().get("memory", {})))

    if json_out:
        rows = []
        for name, desc in ALL_BACKENDS.items():
            rows.append({
                "name": name,
                "description": desc,
                "active": name in active_set,
            })
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

    print("\n  Use 'hermes multi add <name>' or 'hermes multi setup'.\n")


# ── Add / Remove ───────────────────────────────────────────────────────────

def _cmd_add(args: argparse.Namespace) -> None:
    """Add a backend to the active config."""
    backend = getattr(args, "backend", "").strip()
    if not backend:
        print("\n  Usage: hermes multi add <backend>\n")
        return

    config = load_config()
    memory_cfg = config.setdefault("memory", {})
    multi_cfg = memory_cfg.setdefault("multi", {})
    backends_dict = multi_cfg.setdefault("backends", {})
    providers_list = memory_cfg.setdefault("providers", [])

    if backend in backends_dict and not _is_disabled(backends_dict[backend]):
        print(f"\n  '{backend}' is already active.\n")
        return
    if backend in providers_list:
        print(f"\n  '{backend}' is already in the providers list.\n")
        return

    backends_dict[backend] = {}
    if backend not in providers_list:
        providers_list.append(backend)

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

    # Check if backend is actually present in any format
    found = False
    multi_cfg = memory_cfg.get("multi", {})
    backends_dict = multi_cfg.get("backends", {})
    providers_list = memory_cfg.get("providers", [])

    if backend in backends_dict or backend in providers_list:
        found = True

    if not found:
        print(f"\n  '{backend}' is not in the active config.\n")
        return

    _remove_backend_from_config(backend, memory_cfg)
    save_config(config)

    remaining = _get_active_backends(memory_cfg)
    if remaining:
        print(f"\n  ✓ Removed '{backend}'. Active: {', '.join(remaining)}\n")
    else:
        print(f"\n  ✓ Removed '{backend}'. No backends active — built-in only.\n")
