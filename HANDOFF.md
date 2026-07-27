# Multi-Memory Plugin — Audit Handoff

**Date:** 2026-07-27
**Version:** 0.13.0 (commit `e2fe677`)
**Branch:** main (pushed to origin)

## Current State

```
560 tests | 100.00% coverage | ruff clean | mypy clean | CI gate 95%
8 source modules | 1092 statements | acyclic import graph
17 test files | 0 assertion-free tests | 0 duplicate tests
```

## What Was Done (Passes 1–14)

### Pass 12: Dead code removal
- Removed unreachable isinstance in `_normalize_tool_schema` (adapters.py)
- Removed dead `--fix` flag and stub auto-fix block from validate command
- Removed dead config assignments in `_cmd_setup_backend`
- Removed dead `config is None` guards in `_cmd_status` and `_cmd_list`
- Replaced `__import__()` with `find_spec()` in `_install_dependencies`
- Added `isinstance(dep, str)` guard for non-string pip deps from YAML
- Coverage: 97.45% → 97.88% (23 uncovered lines, down from 28)

### Pass 13: Test quality overhaul
- Fixed `TestMultiCommandAllDispatch`: wrong attribute name (`command=` → `multi_command=`) — all 6 dispatch tests silently hit usage-help branch
- Added capsys output assertions to 14 `TestCmdStatusDisplayBranches` tests
- Added delegate call assertions to 7 exception isolation tests
- Added mock assertions to install deps, setup, validate, audit coverage tests
- Replaced `contextlib.suppress` with `pytest.raises` in close() test
- Consolidated 43 `_is_disabled` tests into single parametrized suite (32 cases)
- Zero assertion-free tests remaining (was 49)
- Coverage: 97.88% → 99.17%

### Delegate audit (3 parallel subagents):

**Source audit findings addressed:**
- Thread safety: `__load_config_impl` `self._subs = validated` now wrapped in `with self._lock:`
- Thread safety: `_loading` flag now protected by `_lock` (read and write)
- API consistency: `on_session_switch` now has explicit `rewound: bool = False` parameter matching the stub ABC and `MultiMemoryProvider`
- Error handling: `_SubProviderAdapter.name` property now has AttributeError fallback to CONFIG_KEY
- Edge case: Added warning log when no backends loaded after validation

**Test quality audit findings:**
- Created `TEST_QUALITY_AUDIT.md` with detailed per-file analysis
- Grade: conftest.py (A), test_budget.py (A-), test_cli_validate.py (A-), test_discovery.py (B+), test_generic_adapter.py (B+)

### Pass 14: 100% coverage
- Added `test_100_percent_coverage.py` with tests for:
  - Adapter name property AttributeError fallback (CONFIG_KEY and class name)
  - Mnemosyne adapter ImportError standalone mode
  - Mnemosyne adapter schema normalization warning
  - Module-level PREFIX validation warning
- Added `test_cli_pass13.py` with tests for:
  - `_print_legacy_provider_config` early return (empty/non-dict)
  - `_print_legacy_provider_config` else branch (no get_status_config)
  - `_cmd_list` non-dict memory config coercion
- Coverage: 99.17% → **100.00%** (1092 statements, 0 missed)

## What Remains

### Nothing — audit is complete

All 10 scan methodology checks pass clean:
1. ✅ Dead code scan — zero private functions with no callers
2. ✅ Import graph — acyclic, verified
3. ✅ Hermes ABC drift — identical as of 2026-07-26
4. ✅ Error logging standard — zero `as e` violations
5. ✅ f-string in logger — zero violations
6. ✅ Stale noqa — zero RUF100 warnings
7. ✅ Test naming — no stale references
8. ✅ AGENT.md accuracy — up to date
9. ✅ CHANGELOG consistency — version matches `_version.py`
10. ✅ CI parity — both local and CI use `--cov-fail-under=95`

### pragma: no cover locations (all legitimate)

| File | Line | Reason |
|------|------|--------|
| `__init__.py:36` | `except ImportError` | Standalone fallback for `tool_error` |
| `__init__.py:46` | `except ImportError` | Standalone stub `MemoryProvider` ABC |
| `__init__.py:193` | `logger.warning` | PREFIX warning — only fires if adapter has empty PREFIX |
| `cli.py:36,51,57` | `except ImportError` | Standalone stubs for Hermes CLI functions |
| `cli.py:233` | `_get_available_backends` | Interactive/Hermes-dependent |
| `cli.py:300` | `_find_provider_dir` | Hermes plugin system |
| `cli.py:311` | `_install_dependencies` | Network/fs — Hermes plugin system |
| `cli.py:416` | `_write_env_vars` | Interactive filesystem |
| `cli.py:456` | `_curses_select` | Interactive curses |
| `cli.py:486` | `_curses_checklist` | Interactive curses |
| `cli.py:517` | `_cmd_setup_wizard` | Interactive curses wizard |
| `cli.py:621` | `_cmd_setup_backend` | Interactive setup |
| `cli.py:641` | `_do_backend_setup` | Interactive config wizard |

### noqa suppressions (all legitimate, rules ARE enabled)

| File | Rules | Why |
|------|-------|-----|
| `__init__.py` (stub ABC) | B027 ×9 | Empty methods in standalone `MemoryProvider` stub |
| `__init__.py:188` | E402 | `from .validate import NamespaceValidator` after module-level code |
| `__init__.py:328,452` | PERF203 ×2 | try/except in loops — per-backend error isolation |
| `cli.py:311` | PLR0911, PLR0912, PLR0915 | `_install_dependencies` — interactive/Hermes-dependent |
| `cli.py:517` | PLR0912, PLR0915 | `_cmd_setup_wizard` — interactive curses picker |
| `cli.py:641` | PLR0912, PLR0915 | `_do_backend_setup` — interactive config wizard |

## Key Files

```
src/multi_memory/
├── __init__.py    (756 lines) — MultiMemoryProvider, register(), _fan_out, _batch_shutdown
├── _version.py    (3 lines)   — __version__ = "0.13.0"
├── adapters.py    (501 lines) — _SubProviderAdapter, _normalize_tool_schema, 9 adapters, _GenericAdapter
├── budget.py      (71 lines)  — ToolBudgetWarning
├── cli.py         (1297 lines)— register_cli, multi_command, all _cmd_* handlers, create_adapter
├── config.py      (154 lines) — _is_disabled, _normalize_multi_config, get_enabled_backends
├── discovery.py   (83 lines)  — discover_backends, installed_backends
└── validate.py    (65 lines)  — NamespaceValidator
```

## Module Dependency Graph (verified acyclic)

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

## Test Files (17 files, 560 tests)

```
tests/test_adapters.py           — core adapter + provider + lifecycle tests (168)
tests/test_cli_robustness.py     — CLI dispatch, edge cases, guards (80)
tests/test_cli.py                — CLI subcommand tests (45)
tests/test_config.py             — config loading, format precedence (32)
tests/test_adapter_robustness.py — close/config_schema, schema cache, re-entrancy (27)
tests/test_api_parity.py         — ABC parity, backup_paths, rewound, JSON contract (27)
tests/test_discovery.py          — backend discovery + installation detection (27)
tests/test_config_robustness.py  — _is_disabled parametrized, _normalize_multi_config (22)
tests/test_budget.py             — ToolBudgetWarning + NamespaceValidator (19)
tests/test_adapters_extra.py     — introspection, fan-out, config error paths (18)
tests/test_cli_fifth_pass.py     — --check, --force, --all, --config-only (17)
tests/test_generic_adapter.py    — _GenericAdapter + _try_generic_backend (13)
tests/test_cli_validate.py       — create_adapter + _cmd_validate (12)
tests/test_audit_coverage.py     — schema validation, _fan_out, inspect.signature (11)
tests/test_100_percent_coverage.py — adapter fallback, import errors, schema warnings (5)
tests/test_cli_pass13.py         — legacy provider config, non-dict memory (4)
tests/conftest.py                — pytest fixtures, hermes-agent path resolution
```

## Verification Commands

```bash
cd /home/c/Desktop/agenda/multi-memory-plugin
source .venv/bin/activate

# Full gate
ruff check src/ tests/ && ruff format --check src/ tests/ && mypy src/ && \
  python -m pytest tests/ --cov=src/multi_memory --cov-report=term-missing --cov-fail-under=100 -q

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

# Assertion-free scan
python3 -c "
import ast, os
for root, dirs, files in os.walk('tests'):
    for f in sorted(files):
        if not f.endswith('.py') or f == 'conftest.py': continue
        path = os.path.join(root, f)
        with open(path) as fh:
            tree = ast.parse(fh.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith('test_'):
                has = any(isinstance(c, ast.Assert) or (isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) and c.func.attr.startswith('assert')) for c in ast.walk(node))
                if not has: print(f'  NO ASSERT: {path}:{node.lineno} {node.name}')"
```

## Design Constraints (Do Not Violate)

1. **One external provider limit** — Hermes allows exactly one. This plugin IS that one.
2. **Standalone mode** — All Hermes imports wrapped in `try/except ImportError` with fallbacks.
3. **Error logging standard** — Every `except` uses `as exc`, logs with `logger.debug/warning`.
4. **No f-strings in logger calls** — Use `%s` formatting for lazy evaluation.
5. **Thread safety** — `_lock` (RLock) protects `_subs` mutations and `_loading` flag. Snapshot-before-dispatch pattern.
6. **Schema validation before registration** — Broken backends are skipped, never registered.
7. **Config precedence** — `multi.backends` dict > `providers` list > `provider` string.
8. **`config.py` and `_version.py` are leaves** — No internal imports allowed.
9. **No `--select` flag with ruff** — It overrides the project's `select` list and produces false RUF100 positives.
