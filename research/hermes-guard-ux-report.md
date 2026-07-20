# Research Report: UX / CLI / Documentation Patterns from multi-memory -> hermes-guard

## Executive Summary

Studied the polished multi-memory plugin (971-line CLI, 5 docs files, curses wizard,
structured status output) and compared it to hermes-guard (no CLI module, minimal
docs, single /guard slash command). Identified 8 specific patterns hermes-guard
should adopt, with file references and concrete recommendations.

---

## Pattern 1: Dedicated CLI Module with argparse Subcommands

**What multi-memory does**
- Full `cli.py` (971 lines) registering `hermes multi {status,list,add,remove,setup}`
- Uses `argparse` subparsers via `register_cli(subparser)` entry point
- Commands are discoverable by Hermes's `discover_plugin_cli_commands()`

**Where the code is**
- `src/multi_memory/cli.py:85-112` — `register_cli()` builds subparser tree
- `src/multi_memory/cli.py:117-144` — `multi_command()` router

**What hermes-guard does now**
- Only a single slash command `/guard [on|off]` registered in `__init__.py:416-428`
- No argparse, no subcommands, no CLI module at all

**Recommendation for hermes-guard**
Create `src/hermes_guard/cli.py` with:
```
hermes guard status      # show current guard state, thresholds, last flags
hermes guard config      # show effective config (env vars + YAML)
hermes guard thresholds  # view/set warn/halt thresholds
hermes guard reset       # reset watchdog / pipeline state
hermes guard test        # run a self-test (score a sample string)
```
Register via `register_cli()` following the same `subparser.add_subparsers()`
pattern as multi-memory.

---

## Pattern 2: Rich Status Display with Sections, Badges, and Health

**What multi-memory does**
- `hermes multi status` prints a structured human-readable report:
  - Section headers with `─` dividers
  - Per-backend blocks: config, plugin installed?, available?, missing env vars?
  - Checkmarks (`✓`) and crosses (`✗`) for health
  - Warnings (`⚠`) for misconfigurations
  - `--json` flag for machine-readable output

**Where the code is**
- `src/multi_memory/cli.py:754-874` — `_cmd_status()`
- Uses plain `print()` with ASCII art, not a table library

**What hermes-guard does now**
- No status command at all
- Display logic exists in `display.py` but is only used for real-time flagged
  text (ANSI red/green), not for guard health/status

**Recommendation for hermes-guard**
Add `hermes guard status` that prints:
```
  Guard status
  ────────────────────────────────────────
  State:        enabled
  Thresholds:   warn=0.60  halt=0.85
  Scorer:       vader
  Halt mode:    interrupt
  Watchdog:     OBSERVE (0 consecutive warns)

  Last flagged:
    [WARN] toxicity=0.72  "..."
    categories: abusive=0.72, manipulative=0.51

  Patterns active:
    • RepetitionDegradation   ✓
    • ToxicityCascade         ✓
    • RefusalLoop             ✓
    • TokenSalad              ✓
    • SelfReferentialDoom     ✓

  Tier 2/3:
    Analyst:   available (LLM facade captured)
    Healer:    available
```
Support `--json` for programmatic use.

---

## Pattern 3: Interactive Setup Wizard

**What multi-memory does**
- `hermes multi setup` launches a curses-based picker with terminal fallback
- Guides user through: pick backend -> configure fields -> auto-install deps
- Writes secrets to `~/.hermes/.env` with `0600` permissions
- Handles "add alongside" vs "replace all" when backends already active

**Where the code is**
- `src/multi_memory/cli.py:438-699` — `_cmd_setup_wizard()`, `_do_backend_setup()`
- `src/multi_memory/cli.py:376-432` — `_curses_select()`, `_curses_checklist()`

**What hermes-guard does now**
- No setup wizard
- Config is purely code-level (`GuardConfig` dataclass + env vars + optional YAML)
- User must edit env vars or YAML manually

**Recommendation for hermes-guard**
Add `hermes guard setup` that interactively asks:
1. Choose sentiment model (vader / future options)
2. Set warn threshold (default 0.60)
3. Set halt threshold (default 0.85)
4. Choose halt mode (interrupt / block / log)
5. Enable/disable corrective nudge
6. Test with a sample toxic string

Write to `~/.hermes/.env` with restricted permissions, same as multi-memory.

---

## Pattern 4: Machine-Readable JSON Output Flag

**What multi-memory does**
- Every CLI command supports `--json` for scripting / dashboard integration
- `status --json` emits: `{provider, active_backends, config_format, installed_plugins}`
- `list --json` emits an array of backend objects

**Where the code is**
- `src/multi_memory/cli.py:91-93` — `--json` argument on status
- `src/multi_memory/cli.py:764-777` — JSON branch in `_cmd_status()`

**What hermes-guard does now**
- `display.py` has a `"structured"` mode that emits JSON, but it's only used
  for per-delta flagged text, not for CLI commands (there are no CLI commands)

**Recommendation for hermes-guard**
- Add `--json` to every CLI command
- Use the existing `format_flagged(..., mode="structured")` and
  `format_healing_diff(..., mode="structured")` infrastructure
- Emit JSON arrays/objects for `status`, `config`, `test` commands

---

## Pattern 5: Comprehensive Documentation Suite

**What multi-memory has**
| File | Purpose |
|------|---------|
| README.md | Install, quickstart, CLI overview, docs links |
| CONFIG.md | Full config reference, per-backend tables, troubleshooting |
| CONTRIBUTING.md | Setup, tests, lint, architecture diagram, adding backends |
| AGENT.md | Instructions for AI assistants — architecture, gotchas, testing |
| CHANGELOG.md | Keep-a-Changelog format, version history |

**What hermes-guard has**
| File | Purpose |
|------|---------|
| README.md | Architecture diagram, install, file map, config table, tests |
| (no CONFIG.md) | Config is documented inline in README table only |
| (no CONTRIBUTING.md) | No contributor guide |
| (no AGENT.md) | No AI assistant instructions |
| (no CHANGELOG.md) | No version history |
| 6 design/PRD/audit docs | Internal research docs, not user-facing |

**Recommendation for hermes-guard**
Create the missing 4 docs:
- **CONFIG.md** — Expand the README config table into full reference with
  env var names, YAML keys, type coercion rules, and examples.
- **CONTRIBUTING.md** — `uv sync --extra test`, `pytest tests/`, `ruff check`,
  architecture diagram (already in README), how to add a new pattern/vector.
- **AGENT.md** — Instructions for AI assistants: plugin entry point (`register()`),
  monkey-patch safety, fail-closed principle, testing patterns (mock LLM facade),
  key files with line counts.
- **CHANGELOG.md** — Start from current state; use Keep-a-Changelog format.

---

## Pattern 6: Error Handling Standard with Visible Feedback

**What multi-memory does**
- Every `except` block captures `as exc`, logs with `logger.warning/debug`,
  and prints user-facing messages
- "Zero tolerance for silent failures" — documented in CONTRIBUTING.md
- CLI prints `⚠` warnings and `✓` confirmations with actionable next steps

**Where the code is**
- `src/multi_memory/cli.py:306-317` — dependency install failure prints manual command
- `CONTRIBUTING.md:88-95` — "Error handling standard" section

**What hermes-guard does now**
- `intercept.py:144-179` — `_guarded_stream_delta()` has bare `except Exception: pass`
  in subscriber loops (lines 174-175, 207-208)
- `__init__.py:141-164` — `_notify_stream_*()` also has bare `except Exception: pass`
- These are intentional (subscriber errors must not break the guard), but
  there is no logging of subscriber failures

**Recommendation for hermes-guard**
- Log subscriber failures at `logger.debug` level (not silent)
- In CLI commands, print `⚠` + actionable message on every error path
- Document the error-handling standard in CONTRIBUTING.md:
  - Tier-1 pipeline failures → fail-closed (halt)
  - Subscriber failures → log at debug, do not halt
  - CLI command failures → print to stderr with exit code 1

---

## Pattern 7: Backend/Component Discovery and Listing

**What multi-memory does**
- `hermes multi list` shows all backends in a table with active markers
- Auto-discovers installed plugins via Hermes plugin system
- Static registry fallback (`ALL_BACKENDS`) for standalone use

**Where the code is**
- `src/multi_memory/cli.py:165-226` — `_get_available_backends()`
- `src/multi_memory/cli.py:880-909` — `_cmd_list()`

**What hermes-guard does now**
- No listing/discovery of components
- Patterns are hardcoded in `patterns.py`, vectors in `vectors.py`
- User cannot see which patterns are active without reading code

**Recommendation for hermes-guard**
Add `hermes guard list` or extend `status` to show:
```
  Active components:
    Patterns:
      • RepetitionDegradation    ✓
      • ToxicityCascade          ✓
      • RefusalLoop              ✓
      • TokenSalad               ✓
      • SelfReferentialDoom      ✓
    Vectors (12):
      abusive, manipulative, gaslighting, ...
    Scorer: vader
```

---

## Pattern 8: Config Validation and Env Var Management

**What multi-memory does**
- `_write_env_vars()` appends/updates env vars in `~/.hermes/.env` with `0600`
- Schema-driven config: each backend declares fields with `key`, `description`,
  `default`, `secret`, `choices`, `env_var`, `url`
- Conditional fields (`when` dict) for dependent config

**Where the code is**
- `src/multi_memory/cli.py:338-370` — `_write_env_vars()`
- `src/multi_memory/cli.py:601-667` — schema-driven field prompting in `_do_backend_setup()`

**What hermes-guard does now**
- `GuardConfig` dataclass with defaults + `_ENV_MAP` dict in `config.py`
- No `.env` writing, no schema definition, no interactive prompting
- YAML loading exists but is minimal (`_apply_yaml_overrides()`)

**Recommendation for hermes-guard**
- Define a `GUARD_SCHEMA` list in `config.py` mirroring multi-memory's pattern:
  ```python
  GUARD_SCHEMA = [
      {"key": "toxicity_threshold_warn", "description": "Warn threshold", "default": 0.6, "env_var": "HERMES_GUARD_TOXICITY_WARN"},
      ...
  ]
  ```
- Use it in the setup wizard for consistent prompting
- Add `_write_env_vars()` equivalent for secrets (if any are added later)

---

## Prioritized Top 3 Recommendations

### 1. Create `src/hermes_guard/cli.py` with `status`, `config`, and `test` commands
**Why first:** This is the biggest UX gap. Users currently have zero visibility
into guard state, thresholds, or health. A status command immediately improves
trust and debuggability. It also establishes the CLI infrastructure for future
commands.

**Effort:** Medium (~200 lines, following multi-memory's argparse pattern)
**Files to create:** `src/hermes_guard/cli.py`
**Files to modify:** `src/hermes_guard/__init__.py` (call `register_cli()` in `register()`)

### 2. Add `--json` output to all CLI commands and expose structured display modes
**Why second:** hermes-guard already has `display.py` with `"structured"` mode,
but it's underutilized. Adding `--json` makes the guard programmatically
observable for dashboards, tests, and external tooling. Very low effort since
infrastructure already exists.

**Effort:** Low (~50 lines)
**Files to modify:** `src/hermes_guard/cli.py` (new), `src/hermes_guard/display.py` (minor)

### 3. Create AGENT.md and CONTRIBUTING.md
**Why third:** These are force-multipliers for future development. The
multi-memory AGENT.md is 276 lines of dense, accurate guidance that prevents
AI assistants from making wrong assumptions. hermes-guard's monkey-patch
approach, fail-closed semantics, and LLM facade patterns are subtle and need
documentation for anyone (human or AI) working on the codebase.

**Effort:** Medium (~150 lines each)
**Files to create:** `AGENT.md`, `CONTRIBUTING.md`

---

## Appendix: File Inventory

### multi-memory (patterns to emulate)
| File | Lines | Role |
|------|-------|------|
| `src/multi_memory/cli.py` | 971 | Full CLI: argparse, wizard, status, list, add, remove |
| `README.md` | 77 | Install, quickstart, CLI overview, docs links |
| `CONFIG.md` | 301 | Per-backend config reference, troubleshooting |
| `CONTRIBUTING.md` | 101 | Setup, tests, lint, architecture, adding backends |
| `AGENT.md` | 276 | AI assistant instructions, architecture, gotchas |
| `CHANGELOG.md` | 234 | Keep-a-Changelog format |

### hermes-guard (current state)
| File | Lines | Role |
|------|-------|------|
| `src/hermes_guard/__init__.py` | 514 | Entry point, /guard command, streaming API |
| `src/hermes_guard/config.py` | 191 | GuardConfig dataclass, env/YAML loading |
| `src/hermes_guard/display.py` | 319 | ANSI/structured/plain flagged + diff output |
| `src/hermes_guard/intercept.py` | 260 | Monkey-patch streaming interception |
| `src/hermes_guard/pipeline.py` | 344 | Tier-1 pipeline wiring |
| `README.md` | 122 | Architecture, install, file map, config table |
| (no cli.py) | — | Missing |
| (no CONFIG.md) | — | Missing |
| (no CONTRIBUTING.md) | — | Missing |
| (no AGENT.md) | — | Missing |
| (no CHANGELOG.md) | — | Missing |
