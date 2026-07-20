# Research Report: Multi-Memory Plugin Patterns for Hermes-Guard

## Scope
Read-only analysis of `/home/c/Desktop/agenda/multi-memory-plugin/` compared against `/home/c/Desktop/agenda/hermes-guard/`. Focus on STRUCTURE and CONVENTIONS, not memory domain logic.

---

## Pattern 1: Plugin YAML — Minimal but Complete Metadata

**What it is:**
The `plugin.yaml` is the first thing Hermes reads. Multi-memory keeps it small (9 lines) but includes every field the loader expects: `name`, `version`, `description`, `kind`, `pip_dependencies`.

**Where in multi-memory:**
`plugin.yaml:1-9`
```yaml
name: multi
version: 0.7.2
description: |
  Run multiple memory providers ...
kind: standalone
pip_dependencies: []
```

**How hermes-guard should adopt it:**
Hermes-guard's `plugin.yaml` is only 4 lines and omits `kind` (has `kind: plugin` but no `pip_dependencies`). It should:
1. Add `pip_dependencies: []` explicitly (even if empty) so the loader knows there are no external deps to install.
2. Expand the `description` to mention the CLI command name (`/guard`) so `hermes plugin list` output is self-documenting.
3. Keep `kind: plugin` (correct for a non-memory plugin) but ensure the field is present.

---

## Pattern 2: Standalone Stub ABC with Graceful Degradation

**What it is:**
Every Hermes import is wrapped in `try/except ImportError` with a standalone fallback. The fallback is not a dummy — it is a minimal ABC that matches the real interface enough for unit tests and standalone scripts to run without Hermes installed.

**Where in multi-memory:**
`src/multi_memory/__init__.py:35-117`
```python
try:
    from agent.memory_provider import MemoryProvider
except ImportError:  # pragma: no cover — standalone stub
    import abc
    class MemoryProvider(abc.ABC):
        name: str = ""
        @abc.abstractmethod
        def is_available(self) -> bool: ...
        ...
```

**How hermes-guard should adopt it:**
Hermes-guard currently has NO standalone stubs for Hermes imports. In `intercept.py` it imports `from run_agent import AIAgent` inside `install()` and silently returns on failure. This is fine for runtime but breaks standalone testing. Hermes-guard should:
1. Add a standalone stub for `AIAgent` (or any other Hermes core class) at module level, gated by `try/except ImportError`, so tests can import `hermes_guard.intercept` without the full Hermes runtime.
2. Document the stub with `# pragma: no cover — standalone fallback` to match multi-memory convention.

---

## Pattern 3: Capability-Checked `register(ctx)` — Defensive Against Multiple Callers

**What it is:**
The `register()` function does not assume `ctx` has every method. It uses `hasattr(ctx, "register_memory_provider")` and `hasattr(ctx, "register_cli_command")` to decide what to register, and includes a detailed docstring explaining which Hermes scanners may call it.

**Where in multi-memory:**
`src/multi_memory/__init__.py:183-217`
```python
def register(ctx) -> None:
    """Entry point — called by Hermes plugin loader.
    Two separate callers may invoke this function:
    * Memory scanner ...
    * General scanner ...
    """
    if hasattr(ctx, "register_memory_provider"):
        provider = MultiMemoryProvider()
        ctx.register_memory_provider(provider)
    if hasattr(ctx, "register_cli_command"):
        from .cli import multi_command, register_cli
        ctx.register_cli_command(...)
```

**How hermes-guard should adopt it:**
Hermes-guard's `register()` already uses `hasattr` checks (good), but it is missing the `register_cli_command` path entirely. It should:
1. Add a `hasattr(ctx, "register_cli_command")` branch that registers a `hermes guard` CLI subcommand (e.g. `status`, `config`, `test`) using the same `(setup_fn, handler_fn)` pattern multi-memory uses.
2. Expand the docstring to explain which scanners call it and what capabilities are optional vs required.
3. Consider registering a `hermes guard status` command that prints the current guard state, thresholds, and last-flagged info — mirroring `hermes multi status`.

---

## Pattern 4: CLI Subcommand Tree with `register_cli()` + `handler_fn()` Separation

**What it is:**
CLI commands are split into two functions: `register_cli(subparser)` builds the argparse tree, and `multi_command(args)` routes to the actual implementation. This separation lets Hermes discover the CLI structure without executing any logic.

**Where in multi-memory:**
`src/multi_memory/cli.py:85-144`
```python
def register_cli(subparser: argparse.ArgumentParser) -> None:
    subs = subparser.add_subparsers(dest="multi_command")
    sp = subs.add_parser("status", help="Show active backends and config")
    ...

def multi_command(args: argparse.Namespace) -> None:
    sub = getattr(args, "multi_command", None)
    if sub == "status":
        _cmd_status(args)
    ...
```

**How hermes-guard should adopt it:**
Hermes-guard has no CLI module at all. It should:
1. Create `src/hermes_guard/cli.py` with `register_cli(subparser)` and `guard_command(args)` following the exact same pattern.
2. Commands to implement: `status` (show thresholds, last flag, subscriber count), `test` (run a quick self-check), `config` (show current config values).
3. Wire the CLI into `register()` via `ctx.register_cli_command(name="guard", setup_fn=register_cli, handler_fn=guard_command, ...)`.

---

## Pattern 5: Centralised Config with Lazy Path Resolution

**What it is:**
Config paths are computed lazily (functions, not module-level constants) so they survive profile switches. The config loader handles `FileNotFoundError`, `PermissionError`, `yaml.YAMLError`, and returns a safe default `{}` on any failure.

**Where in multi-memory:**
`src/multi_memory/config.py:23-59`
```python
def _get_hermes_home() -> str:
    return os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))

def _get_config_path() -> str:
    return os.path.join(_get_hermes_home(), "config.yaml")

def load_multi_config() -> dict[str, Any]:
    try:
        with open(cfg_path) as f:
            cfg = yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.debug("[multi-memory] config not found at %s", cfg_path)
        return {}
    except (PermissionError, IsADirectoryError, yaml.YAMLError) as exc:
        logger.warning("[multi-memory] failed to read config at %s: %s", cfg_path, exc)
        return {}
```

**How hermes-guard should adopt it:**
Hermes-guard's `config.py` already has good env-var mapping and YAML loading, but it does NOT read from `~/.hermes/config.yaml`. It should:
1. Add a `_get_hermes_home()` helper and default YAML path under `~/.hermes/config.yaml` (looking for a `guard:` section).
2. Make `load_config()` read the Hermes config first, then apply env overrides, matching multi-memory's precedence.
3. Add `FileNotFoundError` / `PermissionError` handling to `_try_load_yaml()` instead of the current broad `except Exception`.

---

## Pattern 6: Schema Validation Before Registration (Fail-Loud, Not Fail-Silent)

**What it is:**
Before a backend is accepted, its `get_tool_schemas()` is called. If it throws, the backend is rejected with a warning log — it is NOT registered partially.

**Where in multi-memory:**
`src/multi_memory/__init__.py:300-312`
```python
validated = []
for adapter in candidates:
    try:
        schemas = adapter.get_tool_schemas()
        validated.append(adapter)
        logger.info("[multi-memory] %s validated (%d tools)", adapter.name, len(schemas))
    except Exception as exc:
        logger.warning(
            "[multi-memory] %s failed schema validation — NOT registered: %s",
            adapter.name, exc,
        )
```

**How hermes-guard should adopt it:**
Hermes-guard's `register()` calls `intercept.install()` but catches the exception broadly and logs a warning. It does not validate that the pipeline actually works before registering hooks. It should:
1. After `intercept.install()`, run a quick validation pass (e.g. `build_pipeline().process_delta("test", agent=None)`) to ensure the scorer, patterns, and watchdog all initialise correctly.
2. If validation fails, skip hook registration and log a clear warning: "guard pipeline failed validation — NOT registering hooks".
3. This prevents a broken guard from silently disabling itself while claiming to be active.

---

## Pattern 7: Thread-Safe Fan-Out with `_snapshot()` + `_fan_out()`

**What it is:**
All mutable state (the sub-provider list) is protected by `threading.RLock`. A `_snapshot()` method returns a copy of the list so iteration is safe even if another thread mutates it. A `_fan_out()` helper eliminates duplicated try/except boilerplate.

**Where in multi-memory:**
`src/multi_memory/__init__.py:337-373`
```python
def _snapshot(self) -> list[_SubProviderAdapter]:
    with self._lock:
        return list(self._subs)

def _fan_out(self, method: str, *args, **kwargs):
    results = []
    for sub in self._snapshot():
        fn = getattr(sub, method, None)
        if not callable(fn):
            continue
        try:
            result = fn(*args, **kwargs)
            results.append((sub, result))
        except Exception as exc:
            logger.warning("[multi-memory] %s::%s(): %s", sub.name, method, exc)
    return results
```

**How hermes-guard should adopt it:**
Hermes-guard already has subscriber lists (`_stream_output_subscribers`, etc.) but iterates them without locks. In gateway mode with concurrent agents, a subscriber could be added/removed mid-iteration. It should:
1. Protect subscriber registries with `threading.RLock`.
2. Add a `_snapshot_subscribers()` helper that copies the list under the lock before iterating.
3. Use the `_fan_out()` pattern in `_notify_stream_output`, `_notify_stream_reasoning`, and `_notify_turn_complete` to centralise exception handling.

---

## Pattern 8: Graceful Shutdown with Timeout

**What it is:**
Sub-provider shutdown runs in a separate thread with a 10-second timeout. If it hangs, it is abandoned with a warning — the main thread never blocks indefinitely.

**Where in multi-memory:**
`src/multi_memory/__init__.py:584-610`
```python
def _close_or_shutdown(sub, name, timeout=10.0):
    import concurrent.futures
    def _do_close():
        close_fn = getattr(sub, "close", None)
        if callable(close_fn):
            close_fn()
        else:
            sub.shutdown()
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_do_close)
            future.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        logger.warning("[multi-memory] shutdown %s timed out after %.0fs — abandoned", name, timeout)
```

**How hermes-guard should adopt it:**
Hermes-guard has no uninstall/shutdown path beyond `uninstall_patch()`. It should:
1. Add a `shutdown()` or `unregister()` function in `__init__.py` that:
   - Calls `intercept.uninstall()`
   - Clears subscriber lists
   - Shuts down any background threads (e.g. if the watchdog ever runs async)
2. If any step could block (e.g. waiting for a thread), wrap it in a timeout like multi-memory does.
3. Register this shutdown via a Hermes hook if one exists (e.g. `on_plugin_unload`).

---

## Pattern 9: Config Display Override (`format_config_display`)

**What it is:**
The provider overrides `format_config_display(config)` to return human-friendly `(key, value)` pairs instead of dumping raw dicts. This makes `hermes memory status` output readable.

**Where in multi-memory:**
`src/multi_memory/__init__.py:247-262`
```python
def format_config_display(self, config: dict) -> list[tuple[str, str]]:
    multi_cfg = config.get("multi", {})
    backends = multi_cfg.get("backends", {})
    if backends:
        items = ", ".join(k if v in ({}, True) else f"{k}({v})" for k, v in backends.items())
        return [("backends", items)]
    ...
```

**How hermes-guard should adopt it:**
Hermes-guard does not implement `format_config_display` at all. If it ever becomes a provider-like plugin (or if Hermes adds a generic `plugin status` command), it should:
1. Add a `format_config_display(config) -> list[tuple[str, str]]` function that shows:
   - `enabled: yes/no`
   - `toxicity_threshold_warn: 0.60`
   - `toxicity_threshold_halt: 0.85`
   - `halt_mode: interrupt`
   - `subscribers: 3`
2. This makes operational debugging much faster than reading raw YAML.

---

## Pattern 10: Interactive Setup Wizard with Curses + Terminal Fallback

**What it is:**
The `hermes multi setup` command provides an interactive curses-based wizard for configuring backends. If curses is unavailable, it falls back to a simple numbered terminal picker. This dramatically improves UX for first-time users.

**Where in multi-memory:**
`src/multi_memory/cli.py:376-432`
```python
def _curses_select(title, items, default=0):
    try:
        from hermes_cli.curses_ui import curses_radiolist
        return curses_radiolist(title, display_items, selected=default)
    except ImportError:
        # Simple terminal fallback
        print(f"\n  {title}\n")
        for i, (label, desc) in enumerate(items):
            marker = "→" if i == default else " "
            print(f"  {marker} [{i}] {label}  {desc}")
        ...
```

**How hermes-guard should adopt it:**
Hermes-guard has NO setup wizard. A new user must manually edit YAML or set env vars. It should:
1. Add `hermes guard setup` CLI command with an interactive wizard that asks:
   - Enable guard? (y/n)
   - Toxicity warn threshold? (default 0.6)
   - Toxicity halt threshold? (default 0.85)
   - Halt mode? (interrupt / block / log)
   - Inject corrective nudge? (y/n)
2. Use the same curses-first, terminal-fallback pattern.
3. Write the result to `~/.hermes/config.yaml` under a `guard:` section.

---

## Bonus Pattern: Namespace Validation at Import Time

**What it is:**
A `NamespaceValidator` runs at module import time to check that all adapter classes have non-empty `PREFIX` attributes. This catches developer errors immediately rather than at runtime.

**Where in multi-memory:**
`src/multi_memory/validate.py:17-55` and `src/multi_memory/__init__.py:157-166`
```python
from .validate import NamespaceValidator
_validator = NamespaceValidator(list(_SUB_CLASSES))
_prefix_warnings = _validator.validate_all()
if _prefix_warnings:
    logger.warning("[multi-memory] %d adapter(s) have empty PREFIX ...", len(_prefix_warnings))
del _validator, _prefix_warnings
```

**How hermes-guard should adopt it:**
Hermes-guard could add a similar import-time check for its pattern registry — e.g. verify that every `Pattern` subclass has a non-empty `name` and `regex`. This would catch pattern author mistakes at import time.

---

## Summary Table

| # | Pattern | Multi-Memory Location | Hermes-Guard Gap |
|---|---------|----------------------|------------------|
| 1 | Complete plugin.yaml | `plugin.yaml` | Missing `pip_dependencies`, short description |
| 2 | Standalone stub ABC | `__init__.py:35-117` | No stubs for Hermes imports |
| 3 | Capability-checked register | `__init__.py:183-217` | Missing `register_cli_command` branch |
| 4 | CLI subcommand tree | `cli.py:85-144` | No CLI module at all |
| 5 | Lazy config paths | `config.py:23-59` | Does not read `~/.hermes/config.yaml` |
| 6 | Schema validation before reg | `__init__.py:300-312` | No pipeline validation in `register()` |
| 7 | Thread-safe fan-out | `__init__.py:337-373` | Subscriber lists unprotected |
| 8 | Graceful shutdown w/ timeout | `__init__.py:584-610` | No shutdown/unregister path |
| 9 | Config display override | `__init__.py:247-262` | No `format_config_display` |
| 10 | Interactive setup wizard | `cli.py:376-432` | No setup wizard |
| B | Import-time validation | `validate.py` + `__init__.py:157-166` | No import-time checks |
