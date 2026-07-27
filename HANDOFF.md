# Multi-Memory Plugin — Audit Handoff

**Date:** 2026-07-26
**Version:** 0.13.0 (commit `36f95c7`)
**Branch:** main (pushed to origin)

## Current State

```
561 tests | 99.54% coverage | ruff clean | mypy clean | CI gate 95%
8 source modules | 1084 statements | acyclic import graph
```

## What Was Done (Passes 1–12)

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

### Pass 12 (previous session)
- Removed unreachable `isinstance` in `_normalize_tool_schema` (adapters.py) — after `isinstance(schema.get("function"), dict)` passes, the inner re-check was dead; replaced with typed `unwrapped: dict` local to satisfy mypy `no-any-return`
- Removed dead `--fix` argparse flag and stub auto-fix block from `_cmd_validate` — help text promised "Attempt to automatically fix common issues" but implementation printed "not yet implemented"
- Removed dead `config`/`memory_cfg` assignments in `_cmd_setup_backend` — loaded config that was never read (`_do_backend_setup` loads its own)
- Removed dead `config is None` guards in `_cmd_status` and `_cmd_list` — `load_config()` returns `{}` on failure, never `None`
- Removed empty `# ── Status ──` section header in cli.py (no code beneath it)
- Replaced `__import__()` with `find_spec()` in `_install_dependencies` — `__import__` executes module code as a side effect; `find_spec` is a pure probe
- Added `isinstance(dep, str)` guard for non-string pip deps from malformed YAML
- Removed stale `test_validate_with_fix_flag` test and dead `args.fix = False` assignments
- Added `test_validate_adapter_raises_exception` — covers the exception handler path in `_cmd_validate`
- Coverage: 97.45% → 97.88% (23 uncovered lines, down from 28)

### Pass 13 (this session)
- Added `tests/test_cli_pass13.py` (4 tests) covering the 3 testable uncovered lines in cli.py:
  - `_print_legacy_provider_config` early return when `top_config` is empty or non-dict (line 1022)
  - `_print_legacy_provider_config` else branch when provider lacks `get_status_config` (lines 1031-1032)
  - `_cmd_list` with non-dict `memory` config coercing to `{}` (line 1153)
- cli.py now at 100% coverage
- Updated AGENT.md key files table with `test_cli_pass13.py`
- Coverage: 97.88% → 99.54% (5 uncovered lines, down from 23)
- Tests: 557 → 561

## What Remains (Next Session)

### Remaining `noqa` Suppressions in Source

All noqa directives are legitimate — they suppress rules that ARE enabled in `pyproject.toml`:

| File | Rules | Why |
|------|-------|-----|
| `__init__.py` (stub ABC) | B027 ×9 | Empty methods in standalone `MemoryProvider` stub — intentional no-op defaults |
| `__init__.py:188` | E402 | `from .validate import NamespaceValidator` after module-level code — must run after `_SUB_CLASSES` is built |
| `__init__.py:328,452` | PERF203 ×2 | try/except in loops — intentional per-backend error isolation |
| `cli.py:311` | PLR0911, PLR0912, PLR0915 | `_install_dependencies` — interactive/Hermes-dependent, `pragma: no cover` |
| `cli.py:517` | PLR0912, PLR0915 | `_cmd_setup_wizard` — interactive curses picker, `pragma: no cover` |
| `cli.py:641` | PLR0912, PLR0915 | `_do_backend_setup` — interactive config wizard, `pragma: no cover` |

**Do NOT run `ruff check --select RUF100`** — the `--select` flag overrides the project's `select` list, making ruff report all suppressions as stale. Use `ruff check src/` (no flags) to verify.

### Remaining Uncovered Lines (5 total, 99.54%)

```
src/multi_memory/__init__.py:193     — import-time PREFIX validation warning (only fires if an adapter has empty PREFIX)
src/multi_memory/adapters.py:381-382 — _MnemosyneAdapter: ImportError on plugins.memory (standalone mode)
src/multi_memory/adapters.py:422-426 — _MnemosyneAdapter: schema normalization warning path
```

All remaining uncovered lines are in `__init__.py` and `adapters.py` — they require a real Hermes installation or specific import failure paths. cli.py is now at 100% coverage.

### Scan Methodology for Next Session

1. **Dead code scan:** `grep -rn "def _" src/ | while read; do grep -c "function_name" src/ tests/; done` — find private functions with zero callers
2. **Import graph:** Run the AST dependency analyzer — verify no new cycles
3. **Hermes ABC drift:** `diff /tmp/hermes-agent-pinned/agent/memory_provider.py /tmp/hermes-agent-latest/agent/memory_provider.py` — check for new methods since last check (was identical as of 2026-07-26)
4. **Error logging standard:** `grep -rn "as e\b" src/` — must be zero
5. **f-string in logger:** `grep -rn 'logger\.\(info\|warning\|debug\|error\)(f"' src/` — must be zero (use `%s` formatting)
6. **Stale noqa:** `ruff check src/` (NO --select flag) — verify no RUF100 warnings
7. **Test naming:** Verify test class names match the function they test (no stale references to deleted functions)
8. **AGENT.md accuracy:** Cross-reference key files table against actual `ls src/multi_memory/ tests/`
9. **CHANGELOG consistency:** Verify version numbers match `_version.py`
10. **CI parity:** Verify `.github/workflows/ci.yml` `--cov-fail-under` matches local gate (both 95%)

### Key Files

```
src/multi_memory/
├── __init__.py    (749 lines) — MultiMemoryProvider, register(), _fan_out, _batch_shutdown
├── _version.py    (3 lines)   — __version__ = "0.13.0"
├── adapters.py    (491 lines) — _SubProviderAdapter, _normalize_tool_schema, 9 adapters, _GenericAdapter
├── budget.py      (71 lines)  — ToolBudgetWarning
├── cli.py         (1297 lines)— register_cli, multi_command, all _cmd_* handlers, create_adapter
├── config.py      (154 lines) — _is_disabled, _normalize_multi_config, get_enabled_backends, MNEMOSYNE_PLUGIN_DIRS
├── discovery.py   (83 lines)  — discover_backends, installed_backends
└── validate.py    (65 lines)  — NamespaceValidator
```

### Module Dependency Graph (verified acyclic)

```
_version.py  (leaf)
config.py    (leaf)
budget.py    (leaf)
validate.py  (leaf)
  ↓
adapters.py  → config
  ↓
__init__.py  → _version, adapters, budget, config, validate
  ↓
discovery.py → config
  ↓
cli.py       → _version, config, __init__ (deferred: adapters via create_adapter)
```

### Test Files (16 files, 561 tests)

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
tests/test_cli_pass13.py         — _print_legacy_provider_config edges, _cmd_list non-dict memory
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
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mod = getattr(node, 'module', None) or ''
            if mod.startswith('multi_memory') or mod.startswith('.'):
                imports.append(mod.split('.')[-1])
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
9. **No `--select` flag with ruff** — It overrides the project's `select` list and produces false RUF100 positives.
