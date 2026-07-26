# Multi-Memory Plugin — Audit Handoff

**Date:** 2026-07-26
**Version:** 0.13.0 (commit `7de6482`)
**Branch:** main (pushed to origin)

## Current State

```
557 tests | 97.45% coverage | ruff clean | mypy clean | CI gate 95%
8 source modules | 2936 lines | acyclic import graph
```

## What Was Done (Passes 1–11)

### Architecture
- `config.py` is the canonical foundation (zero internal imports)
- `_version.py` is the single source of `__version__`
- `_normalize_multi_config()` lives in `config.py` (moved from `__init__.py`)
- `MNEMOSYNE_PLUGIN_DIRS` centralized in `config.py`
- `_get_active_backends()` deleted from `cli.py` — replaced by `config.get_enabled_backends()`
- `create_adapter()` in `cli.py` reuses `_SUB_CLASSES_BY_KEY` from `__init__.py` (no duplicate registry)
- `_cmd_status` extracted into `_print_config_value()`, `_print_legacy_provider_config()`, `_print_backend_status()`

### Custom Backend Compatibility
- `_normalize_tool_schema()` mirrors upstream `agent.memory_manager.normalize_tool_schema`
- Double-wrapped OpenAI schemas unwrapped in all three schema paths
- `_renorm_schemas()` skips nameless schemas (was producing `"prefix_"`)
- All lifecycle methods forward `**kwargs` (sync_turn, prefetch, queue_prefetch)
- Hermes ABC parity verified against both pinned `v2026.7.7.2` and latest `main`

### CLI UX
- `hermes multi validate` command added
- `hermes multi list` shows categorized backends (Local/Cloud via `BACKEND_CATEGORIES`)
- `hermes multi remove` confirms before removing (bypass with `--force`)
- `hermes multi add` installs dependencies (skip with `--config-only`)
- `hermes multi update --check` previews without installing
- All argparse descriptions enhanced

### Hygiene
- All `as e` → `as exc` per error logging standard
- Dead `--non-interactive` flag removed
- Dead uncategorized backends code path removed
- Dead `import sys` (×2), redundant `from typing import cast` (×4) removed
- Orphaned `setup.cfg` deleted
- CHANGELOG duplicate `0.12.0` headers merged
- Version aligned to `0.13.0` across `_version.py`, `pyproject.toml`, `plugin.yaml`

## What Remains (Next Session)

### Remaining `noqa` Suppressions in `cli.py`

Three functions still carry `# noqa: PLR0912, PLR0915` (too many branches/statements):

| Function | Lines | Why |
|----------|-------|-----|
| `_do_backend_setup` | 149 | Interactive per-backend config wizard — iterates schema fields, handles secrets/choices/defaults/env vars |
| `_cmd_setup_wizard` | 101 | Interactive curses picker — builds item list, handles remove/add/built-in-only paths |
| `_install_dependencies` | 97 | Dependency installer — uv/pip fallback, external dep checks, error reporting |

All three are `# pragma: no cover` (interactive/Hermes-dependent). Refactoring them is high-risk (breaking interactive flows) but would eliminate the last lint suppressions.

**Approach for `_do_backend_setup`:** Extract field-type handlers into a dispatch dict:
```python
_FIELD_HANDLERS = {
    "choices": _handle_choice_field,
    "secret": _handle_secret_field,
    "default": _handle_default_field,
}
```

**Approach for `_cmd_setup_wizard`:** Extract the remove-backend sub-flow and the picker-building logic into helpers.

**Approach for `_install_dependencies`:** Extract uv/pip command building and external dep checking into helpers.

### Remaining Uncovered Lines (28 total, 97.45%)

```
src/multi_memory/__init__.py:193     — import-time PREFIX validation warning (only fires if an adapter has empty PREFIX)
src/multi_memory/adapters.py:70      — _normalize_tool_schema: schema["function"] not a dict after unwrap
src/multi_memory/adapters.py:382-383 — _MnemosyneAdapter: ImportError on plugins.memory (standalone mode)
src/multi_memory/adapters.py:423-427 — _MnemosyneAdapter: schema normalization warning path
src/multi_memory/cli.py:204-210      — multi_command dispatch: setup with/without backend arg
src/multi_memory/cli.py:1001-1002    — _cmd_validate: adapter.is_available() == False path
src/multi_memory/cli.py:1039-1051    — _print_legacy_provider_config: get_status_config path
src/multi_memory/cli.py:1097         — _print_backend_status: not-available env var display
src/multi_memory/cli.py:1147         — _cmd_status: legacy provider warning
src/multi_memory/cli.py:1173,1176    — _cmd_list: show_all flag paths
```

Most are interactive/Hermes-dependent paths. The testable ones:
- `cli.py:1001-1002` — mock `create_adapter` to return an adapter with `is_available() == False`
- `cli.py:1173,1176` — pass `show_all=True` to `_cmd_list` (already tested in `test_cli_fifth_pass.py` but the assertion path may differ)

### Scan Methodology for Next Session

1. **Dead code scan:** `grep -rn "def _" src/ | while read; do grep -c "function_name" src/ tests/; done` — find private functions with zero callers
2. **Import graph:** Run the AST dependency analyzer (see pass 4) — verify no new cycles
3. **Hermes ABC drift:** `diff /tmp/hermes-agent-pinned/agent/memory_provider.py /tmp/hermes-agent-latest/agent/memory_provider.py` — check for new methods since last check (was identical as of 2026-07-26)
4. **Error logging standard:** `grep -rn "as e\b" src/` — must be zero
5. **f-string in logger:** `grep -rn 'logger\.\(info\|warning\|debug\|error\)(f"' src/` — must be zero (use `%s` formatting)
6. **Stale noqa:** `ruff check --select RUF100 src/` — find suppressions for rules that no longer fire
7. **Test naming:** Verify test class names match the function they test (no stale references to deleted functions)
8. **AGENT.md accuracy:** Cross-reference key files table against actual `ls src/multi_memory/ tests/`
9. **CHANGELOG consistency:** Verify version numbers match `_version.py`
10. **CI parity:** Verify `.github/workflows/ci.yml` `--cov-fail-under` matches local gate (both 95%)

### Key Files

```
src/multi_memory/
├── __init__.py    (749 lines) — MultiMemoryProvider, register(), _fan_out, _batch_shutdown
├── _version.py    (3 lines)   — __version__ = "0.13.0"
├── adapters.py    (493 lines) — _SubProviderAdapter, _normalize_tool_schema, 9 adapters, _GenericAdapter
├── budget.py      (71 lines)  — ToolBudgetWarning
├── cli.py         (1318 lines)— register_cli, multi_command, all _cmd_* handlers, create_adapter
├── config.py      (154 lines) — _is_disabled, _normalize_multi_config, get_enabled_backends, MNEMOSYNE_PLUGIN_DIRS
├── discovery.py   (83 lines)  — discover_backends, installed_backends
└── validate.py    (65 lines)  — NamespaceValidator
```

### Module Dependency Graph (verified acyclic)

```
_version.py  (leaf)
config.py    (leaf)
  ↓
adapters.py  → config
  ↓
__init__.py  → config, adapters, budget, validate
  ↓
discovery.py → config
  ↓
cli.py       → _version, config, __init__ (deferred: adapters via create_adapter)
```

### Test Files (15 files, 557 tests)

```
tests/test_adapters.py           — core adapter + provider + lifecycle tests
tests/test_adapters_extra.py     — introspection, fan-out, config error paths
tests/test_adapter_robustness.py — close/config_schema, schema cache, re-entrancy, prefix routing
tests/test_api_parity.py         — ABC parity, backup_paths, rewound, JSON contract
tests/test_audit_coverage.py     — schema validation, _fan_out, inspect.signature, discovery
tests/test_budget.py             — ToolBudgetWarning + NamespaceValidator
tests/test_cli.py                — CLI subcommand tests
tests/test_cli_robustness.py     — CLI dispatch, edge cases, guards
tests/test_cli_validate.py       — create_adapter + _cmd_validate
tests/test_cli_fifth_pass.py     — --check, --force, --all, --config-only, categorized list
tests/test_config.py             — config loading, format precedence
tests/test_config_robustness.py  — _is_disabled, _normalize_multi_config, edge cases
tests/test_discovery.py          — backend discovery + installation detection
tests/test_generic_adapter.py    — _GenericAdapter + _try_generic_backend
tests/conftest.py                — pytest fixtures, hermes-agent path resolution
```

### Verification Commands

```bash
cd /home/c/Desktop/agenda/multi-memory-plugin
source .venv/bin/activate

# Full gate
ruff check src/ tests/ && ruff format --check src/ tests/ && mypy src/ && \
  python -m pytest tests/ --cov=src/multi_memory --cov-report=term-missing --cov-fail-under=95 -q

# Quick smoke
python -m pytest tests/ -x -q

# Import graph
python3 -c "
import ast, os
src = 'src/multi_memory'
for f in sorted(os.listdir(src)):
    if not f.endswith('.py'): continue
    with open(os.path.join(src, f)) as fh:
        tree = ast.parse(fh.read())
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith('multi_memory'):
            imports.append(node.module.split('.')[-1])
    print(f'{f}: {imports or \"(leaf)\"}')"

# Hermes ABC check (requires /tmp/hermes-agent-latest)
diff /tmp/hermes-agent-pinned/agent/memory_provider.py /tmp/hermes-agent-latest/agent/memory_provider.py
```

### Design Constraints (Do Not Violate)

1. **One external provider limit** — Hermes allows exactly one. This plugin IS that one.
2. **Standalone mode** — All Hermes imports wrapped in `try/except ImportError` with fallbacks.
3. **Error logging standard** — Every `except` uses `as exc`, logs with `logger.debug/warning`.
4. **No f-strings in logger calls** — Use `%s` formatting for lazy evaluation.
5. **Thread safety** — `_lock` (RLock) protects `_subs` mutations. Snapshot-before-dispatch pattern.
6. **Schema validation before registration** — Broken backends are skipped, never registered.
7. **Config precedence** — `multi.backends` dict > `providers` list > `provider` string.
8. **`config.py` and `_version.py` are leaves** — No internal imports allowed.
