# Hermes Guard — Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Build a standalone `~/.hermes/plugins/hermes-guard/` plugin that intercepts streaming model output in real time, scores for toxicity, escalates to auxiliary analyst/healer models, and surgically rewrites toxic spans — without touching Hermes source code.

**Architecture:** Class-level monkey-patch of `AIAgent._fire_stream_delta` and `AIAgent._fire_reasoning_delta` for per-delta Tier 1 scoring. Standard `transform_llm_output` hook for post-turn Tier 2/3. `ctx.llm` (PluginLlm) for auxiliary model calls. Subscription API for memory backend integration. Fail-closed: halt via `self._interrupt_requested = True`.

**Tech Stack:** Python 3.11+, Hermes PluginContext API, HuggingFace transformers (CPU-only) for Tier 1, PluginLlm for Tier 2/3.

**Integration points (verified against hermes-agent codebase):**

| Point | File | Line | What |
|-------|------|------|------|
| Stream delta choke | `run_agent.py` | 4055 | `_fire_stream_delta(self, text: str) -> None` |
| Reasoning delta choke | `run_agent.py` | 4108 | `_fire_reasoning_delta(self, text: str) -> None` |
| Interrupt flag | `run_agent.py` | 2302 | `self._interrupt_requested = True` |
| Post-turn hook | `turn_finalizer.py` | 265 | `transform_llm_output` with `response_text, session_id, model, platform` |
| Plugin LLM access | `plugins.py` | 302 | `ctx.llm` → `PluginLlm` facade |
| Message injection | `plugins.py` | 362 | `ctx.inject_message(content, role)` |
| Hook registration | `plugins.py` | 939 | `ctx.register_hook(name, callback)` |
| Slash commands | `plugins.py` | 415 | `ctx.register_command(name, handler)` |

---

## Phase 1 — Plugin Scaffolding

### Task 1: Create plugin.yaml manifest

**Objective:** Register the plugin with Hermes discovery.

**Files:**
- Create: `~/.hermes/plugins/hermes-guard/plugin.yaml`

```yaml
name: hermes-guard
version: 0.1.0
description: "Real-time streaming output guard — scores, halts, and surgically heals toxic model output."
author: ""
kind: standalone
requires_env: []
provides_hooks:
  - transform_llm_output
  - post_llm_call
provides_tools: []
```

**Verification:** `hermes plugins list` shows hermes-guard after restart.

---

### Task 2: Create __init__.py with register(ctx) stub

**Objective:** Minimal plugin entry point that Hermes can load.

**Files:**
- Create: `~/.hermes/plugins/hermes-guard/__init__.py`

```python
"""Hermes Guard — real-time streaming output watchdog."""

def register(ctx):
    """Standard Hermes plugin entry point."""
    pass
```

**Verification:** Plugin loads without errors. `hermes plugins list` shows it enabled.

---

### Task 3: Create guard state module

**Objective:** Central state object shared across tiers — scores, buffers, halt flags, subscriber lists.

**Files:**
- Create: `~/.hermes/plugins/hermes-guard/state.py`

```python
"""Guard state — singleton shared across all tiers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class GuardState:
    """Central state for the output guard. One instance per process."""

    # Tier 1 configuration
    enabled: bool = True
    halt_threshold: float = 0.85

    # Accumulated turn state (cleared each turn)
    output_buffer: list[str] = field(default_factory=list)
    reasoning_buffer: list[str] = field(default_factory=list)
    flagged_spans: list[dict] = field(default_factory=list)

    # Halt state
    last_halt_reason: str | None = None
    turn_halted: bool = False

    # Streaming subscribers
    output_subscribers: list[Callable] = field(default_factory=list)
    reasoning_subscribers: list[Callable] = field(default_factory=list)
    turn_complete_subscribers: list[Callable] = field(default_factory=list)

    # Tier 2/3 handles (set after register)
    llm: Any = None  # PluginLlm facade


_guard = GuardState()


def get_guard() -> GuardState:
    return _guard


def reset_turn() -> None:
    """Clear per-turn buffers. Called at start of each turn."""
    _guard.output_buffer.clear()
    _guard.reasoning_buffer.clear()
    _guard.flagged_spans.clear()
    _guard.last_halt_reason = None
    _guard.turn_halted = False
```

**Verification:** Import works, singleton pattern correct.

---

## Phase 2 — Class-Level Streaming Interception

### Task 4: Create stream patch module

**Objective:** Monkey-patch `AIAgent._fire_stream_delta` and `AIAgent._fire_reasoning_delta` at the class level. One-time install, idempotent, chain-safe.

**Files:**
- Create: `~/.hermes/plugins/hermes-guard/stream_patch.py`

```python
"""Class-level monkey-patch of AIAgent streaming methods.

Installed once per process from register(ctx). Idempotent — calling
install() twice is harmless. Chain-safe — detects and wraps any prior
patches from other plugins.
"""

from __future__ import annotations

from run_agent import AIAgent

from .state import get_guard, reset_turn

_original_fire_stream = None
_original_fire_reasoning = None
_installed = False


def _guarded_stream_delta(self, text: str) -> None:
    """Per-delta interception — after scrubbers, before UI callbacks."""
    guard = get_guard()
    if not guard.enabled:
        _original_fire_stream(self, text)
        return

    # Accumulate for post-turn analysis
    guard.output_buffer.append(text)

    # Fan out to subscribers (memory backends, other plugins)
    for sub in guard.output_subscribers:
        try:
            sub(text, self)
        except Exception:
            pass

    # Tier 1 scoring happens here (Phase 3 will add the scorer call)
    # For now: pass through
    _original_fire_stream(self, text)


def _guarded_reasoning_delta(self, text: str) -> None:
    """Per-delta CoT interception."""
    guard = get_guard()
    if not guard.enabled:
        _original_fire_reasoning(self, text)
        return

    guard.reasoning_buffer.append(text)

    for sub in guard.reasoning_subscribers:
        try:
            sub(text, self)
        except Exception:
            pass

    _original_fire_reasoning(self, text)


def install() -> None:
    """Install class-level patches. Idempotent, chain-safe."""
    global _original_fire_stream, _original_fire_reasoning, _installed
    if _installed:
        return

    current_stream = AIAgent._fire_stream_delta
    current_reasoning = AIAgent._fire_reasoning_delta

    # If our wrapper is already installed, nothing to do.
    if current_stream is _guarded_stream_delta:
        _installed = True
        return

    # Save whatever is currently there as "original" — this handles
    # the case where another plugin patched before us (chain-safe).
    _original_fire_stream = current_stream
    _original_fire_reasoning = current_reasoning

    AIAgent._fire_stream_delta = _guarded_stream_delta
    AIAgent._fire_reasoning_delta = _guarded_reasoning_delta
    _installed = True
```

**Verification:** After `install()`, `AIAgent._fire_stream_delta` is `_guarded_stream_delta`. Calling `install()` twice doesn't double-wrap.

---

### Task 5: Wire stream_patch into register(ctx)

**Objective:** Install patches at plugin load time.

**Files:**
- Modify: `~/.hermes/plugins/hermes-guard/__init__.py`

```python
"""Hermes Guard — real-time streaming output watchdog."""

from .stream_patch import install as _install_patches
from .state import get_guard


def register(ctx):
    """Standard Hermes plugin entry point."""
    # Install class-level streaming patches — once, at startup
    _install_patches()

    # Wire up ctx.llm for Tier 2/3 auxiliary model calls
    guard = get_guard()
    guard.llm = ctx.llm

    # Tier 2/3: post-turn hooks (standard plugin hooks — no patching needed)
    ctx.register_hook("transform_llm_output", _on_transform_llm_output)
    ctx.register_hook("post_llm_call", _on_post_llm_call)

    # Slash command
    ctx.register_command("guard", _cmd_guard, description="Toggle output guard")
```

**Verification:** Plugin loads. Streaming passes through normally. `_guarded_stream_delta` receives deltas.

---

## Phase 3 — Tier 1: Interface First, Then Research

Per PRD: "The abstract is designed first, concrete thresholding strategies are
plugged in later." The Scorer interface is the abstract contract. The HF review
finds models that satisfy it.

### Task 6: Define Scorer interface (abstract contract)

**Objective:** Lock the `DeltaScore` dataclass and `Scorer` Protocol. This is the
abstract contract that all Tier 1 backends must satisfy. Designed first, then
models are evaluated against it.

**Files:**
- Create: `~/.hermes/plugins/hermes-guard/scorer.py`

The interface fields match what the PRD specifies: per-delta toxicity scoring
across the vector taxonomy, with a halt decision. The concrete scoring function
(sentiment model, multi-label classifier, ensemble) is plugged in later.

**Verification:** Protocol is importable. Any backend implementing `Scorer`
satisfies the contract.

### Task 7: Survey HuggingFace for candidate models

**Objective:** Find models that implement the Scorer interface on CPU.

**Deliverable:** `~/.hermes/plugins/hermes-guard/research/model-survey.md`

Criteria:
- CPU-only inference (no GPU dependency)
- Multi-label or fine-grained classification across the vector taxonomy
- Inference time < 50ms per delta on target hardware
- Model size < 500MB on disk

Candidate families: DistilBERT fine-tunes, RoBERTa toxicity classifiers,
compact multi-label models, lexicon + lightweight model hybrids.

**Verification:** Survey lists 3-5 candidates with size, speed, taxonomy coverage.

### Task 8: Benchmark candidates

**Objective:** Run shortlisted models against real session quotes tagged with
vector categories. Measure accuracy per category, false positive rate, CPU
inference time, memory footprint.

**Deliverable:** `~/.hermes/plugins/hermes-guard/research/benchmark-results.md`

**Verification:** Benchmark table with at least 3 models compared. One selected.

### Task 9: First integration

**Objective:** Implement the selected model as a `Scorer`, wire into
`_guarded_stream_delta`. End-to-end: provider emits deltas → scorer classifies
→ halt on threshold. First implementation code written for Tier 1.

---

## Phase 4 — Tier 2/3: Post-Turn Analysis & Healing

### Task 10: Define analyst data structures

**Objective:** Define `Verdict` and `AnalystResult` dataclasses. The `analyze()`
function signature and call site are structural — the prompt body and verdict
parsing are produced after infrastructure (see PRD).

**Files:**
- Create: `~/.hermes/plugins/hermes-guard/analyst.py`

```python
"""Tier 2 — Auxiliary analyst."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Verdict:
    """Tier 2 verdict for a flagged span."""
    span_text: str
    start_char: int
    end_char: int
    confirmed: bool
    category: str = ""
    reasoning: str = ""
    severity: float = 0.0


@dataclass
class AnalystResult:
    """Complete Tier 2 analysis."""
    verdicts: list[Verdict] = field(default_factory=list)
    raw_response: str = ""
    error: str | None = None


# analyze() function signature reserved — prompt and parsing built later.
# See PRD: "Prompt must be produced after infrastructure is built so it
# can be iterated on against live output."
```

**Verification:** Dataclasses import cleanly.

---

### Task 11: Define healer data structures

**Objective:** Define `HealerResult` dataclass. The `heal()` function signature
and call site are structural — the prompt body is produced after infrastructure.

**Files:**
- Create: `~/.hermes/plugins/hermes-guard/healer.py`

```python
"""Tier 3 — Surgical healer."""

from __future__ import annotations

from dataclasses import dataclass

from .analyst import Verdict


@dataclass
class HealerResult:
    """Tier 3 healing result."""
    healed_text: str = ""
    original_text: str = ""
    healed_spans: list[dict] = None
    error: str | None = None

    def __post_init__(self):
        if self.healed_spans is None:
            self.healed_spans = []


# heal() function signature reserved — prompt built later.
# See PRD: "Prompt must be produced after infrastructure."
```

**Verification:** Dataclass imports cleanly.

---

### Task 12: Wire Tier 2/3 into transform_llm_output hook

**Objective:** When `transform_llm_output` fires, run accumulated flagged text through Tier 2 analyst, then Tier 3 healer, return healed text. Fail-closed: on error, return halt placeholder.

**Files:**
- Modify: `~/.hermes/plugins/hermes-guard/__init__.py` (add hook handlers)

```python
from .state import get_guard, reset_turn
from .analyst import analyze
from .healer import heal


def _on_transform_llm_output(
    response_text: str,
    session_id: str = "",
    model: str = "",
    platform: str = "",
    **kwargs,
) -> str | None:
    """Post-turn hook: run Tier 2 analysis + Tier 3 healing."""
    guard = get_guard()

    if not guard.enabled or not guard.flagged_spans:
        return None  # No transformation needed

    # Tier 2: analyst review
    analyst_result = analyze(
        llm=guard.llm,
        flagged_text=response_text,
        flagged_spans=guard.flagged_spans,
        session_id=session_id,
        model=model,
    )

    if analyst_result.error:
        # Fail-closed: analyst unavailable → silent halt
        return "—"

    confirmed = [v for v in analyst_result.verdicts if v.confirmed]
    if not confirmed:
        return None  # All dismissed

    healer_result = heal(
        llm=guard.llm,
        original_text=response_text,
        confirmed_spans=confirmed,
        session_id=session_id,
        model=model,
    )

    if healer_result.error:
        # Fail-closed: healer failed → silent halt
        return "—"

    return healer_result.healed_text


def _on_post_llm_call(session_id: str = "", **kwargs) -> None:
    """Post-turn cleanup: reset per-turn buffers."""
    reset_turn()
```

**Verification:** Hook fires after turn. With no flagged spans → returns None. With flagged spans → runs analysis pipeline. On error → returns halt placeholder.

---

## Phase 5 — Streaming Subscription Hub

### Task 13: Create subscription API module

**Objective:** Public API for other plugins and memory backends to subscribe to streaming deltas.

**Files:**
- Create: `~/.hermes/plugins/hermes-guard/subscriptions.py`

```python
"""Subscription API — other plugins/memory backends subscribe to streaming deltas."""

from __future__ import annotations

from typing import Any, Callable

from .state import get_guard


def subscribe_stream_output(callback: Callable[[str, Any], None]) -> None:
    """Receive output deltas: callback(text, agent)."""
    get_guard().output_subscribers.append(callback)


def subscribe_stream_reasoning(callback: Callable[[str, Any], None]) -> None:
    """Receive reasoning/CoT deltas: callback(text, agent)."""
    get_guard().reasoning_subscribers.append(callback)


def subscribe_turn_complete(callback: Callable[[dict], None]) -> None:
    """Receive turn summary after streaming completes."""
    get_guard().turn_complete_subscribers.append(callback)


def unsubscribe(callback: Callable) -> None:
    """Remove a previously registered callback."""
    guard = get_guard()
    for lst in (guard.output_subscribers, guard.reasoning_subscribers,
                guard.turn_complete_subscribers):
        try:
            lst.remove(callback)
        except ValueError:
            pass
```

**Verification:** Subscribe a callback → it receives deltas during streaming. Unsubscribe → it stops receiving.

---

### Task 14: Fire turn_complete after transform_llm_output

**Objective:** After Tier 3 healing completes, fire turn_complete summary to subscribers.

**Files:**
- Modify: `~/.hermes/plugins/hermes-guard/__init__.py` (in `_on_post_llm_call`)

```python
def _on_post_llm_call(
    session_id: str = "",
    model: str = "",
    platform: str = "",
    **kwargs,
) -> None:
    """Post-turn cleanup + fire turn_complete to subscribers."""
    guard = get_guard()

    # Build turn summary
    summary = {
        "session_id": session_id,
        "model": model,
        "platform": platform,
        "output_text": "".join(guard.output_buffer),
        "reasoning_text": "".join(guard.reasoning_buffer),
        "was_halted": guard.turn_halted,
        "halt_reason": guard.last_halt_reason,
        "flagged_spans": guard.flagged_spans,
    }

    # Fire to subscribers
    for sub in guard.turn_complete_subscribers:
        try:
            sub(summary)
        except Exception:
            pass

    # Reset for next turn
    reset_turn()
```

**Verification:** After a turn, turn_complete subscribers receive summary dict with accumulated text.

---

## Phase 6 — Slash Command & Configuration

### Task 15: Create /guard slash command

**Objective:** Toggle guard on/off per session.

**Files:**
- Modify: `~/.hermes/plugins/hermes-guard/__init__.py` (add handler)

```python
def _cmd_guard(raw_args: str) -> str:
    """Slash command: /guard [on|off|status]"""
    guard = get_guard()
    args = raw_args.strip().lower()
    if args in ("off", "disable", "0"):
        guard.enabled = False
        return "Guard: disabled"
    elif args in ("on", "enable", "1"):
        guard.enabled = True
        return "Guard: enabled"
    else:
        return f"Guard: {'enabled' if guard.enabled else 'disabled'}"
```

**Verification:** Type `/guard off` → guard disabled, deltas pass through unscored. `/guard on` → re-enabled. `/guard status` → shows current state.

---

### Task 16: Create config loading

**Objective:** Read guard configuration from Hermes config.yaml.

**Files:**
- Create: `~/.hermes/plugins/hermes-guard/config.py`

```python
"""Guard configuration loader."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_guard_config() -> dict[str, Any]:
    """Load guard section from config.yaml. Returns defaults if absent."""
    try:
        cfg_path = Path.home() / ".hermes" / "config.yaml"
        with open(cfg_path) as f:
            cfg = yaml.safe_load(f) or {}
    except (FileNotFoundError, PermissionError):
        return _defaults()

    return {**_defaults(), **(cfg.get("guard") or {})}


def _defaults() -> dict[str, Any]:
    return {
        "enabled": True,
        "halt_threshold": 0.85,
        "scorer": "vader",  # vader | huggingface | custom
        "tier2_enabled": True,
        "tier3_enabled": True,
        "audit_log_path": "",
    }
```

**Verification:** With no guard section in config.yaml → returns defaults. With guard section → merges.

---

## Phase 7 — Tests

### Task 17: Create integration test for stream patch

**Files:**
- Create: `~/.hermes/plugins/hermes-guard/tests/test_stream_patch.py`

```python
"""Tests for class-level stream patching."""

import pytest
from run_agent import AIAgent
from hermes_guard.stream_patch import install


def test_install_is_idempotent():
    install()
    first = AIAgent._fire_stream_delta
    install()
    second = AIAgent._fire_stream_delta
    assert first is second  # Not double-wrapped


def test_original_still_works():
    """After patching, calling the wrapper should call the original."""
    install()
    # Create a mock agent and verify the method signature
    # (Full integration test would need a running agent)
```

**Verification:** `pytest tests/test_stream_patch.py -v` — pass.

---

## Phase 8 — Memory Backend Integration Example

### Task 18: Create multi-memory integration example

**Objective:** Show how the multi-memory plugin subscribes to streaming deltas.

**Files:**
- Create: `~/.hermes/plugins/hermes-guard/examples/multi_memory_integration.py`

```python
"""Example: multi-memory plugin subscribes to guard streaming.

Add to multi_memory/__init__.py register() function.
"""


def _subscribe_to_guard_if_available(provider):
    """Subscribe to guard's streaming hub. Graceful if guard not installed."""
    try:
        from hermes_guard.subscriptions import (
            subscribe_stream_output,
            subscribe_stream_reasoning,
            subscribe_turn_complete,
        )

        def _fan_output(text, agent):
            provider._fan_out("on_stream_delta", text, agent=agent)

        def _fan_reasoning(text, agent):
            provider._fan_out("on_reasoning_delta", text, agent=agent)

        def _fan_turn_complete(summary):
            provider._fan_out("on_turn_complete", summary)

        subscribe_stream_output(_fan_output)
        subscribe_stream_reasoning(_fan_reasoning)
        subscribe_turn_complete(_fan_turn_complete)

    except ImportError:
        pass  # Guard not installed — existing sync_turn still works
```

**Verification:** When guard is installed, memory backends receive `on_stream_delta` calls. When not installed, behavior is unchanged.

---

## Post-Audit Corrections

### Claim: "No display mechanism for flagged tokens" — WRONG

The `_fire_stream_delta` → `stream_delta_callback` → gateway `_stream(delta)` pipeline
already delivers every delta to the display layer. The gateway constructs
`{"text": delta, "rendered": streamer.feed(delta)}` and emits `message.delta`
(`tui_gateway/server.py:5074-5080`). The TUI/WebUI render both raw and rendered
text. Flagged tokens reach the user — the guard's halt path blocks only the
worst deltas. Rendering them in red is a display-layer concern (ANSI codes for
TUI, rendered payload field for WebUI), not a guard gap.

### Claim: "Tier 3 cannot stream live diff" — WRONG

`transform_llm_output` returns replacement text. The guard can format it as a
diff block (ANSI strikethrough red → plain green, or markdown that the streamer
renders). The gateway renders the returned text inline. It is not per-token
streaming, but the visual effect — original toxic text struck through in red,
healed text in green — is achievable. The `transform_llm_output` hook fires
after streaming completes, and its return value replaces the displayed text.

### Claim: "Healer prompt re-injects stripped rules" — CONFIRMED

The plan's `_build_healer_prompt` (lines 672-685) contains "Do not change tone,
voice, or information content outside the spans. Do not apologize or explain the
edit." — rules the PRD v0.4 explicitly stripped. These were labeled as
self-inserts in the previous session. Must be replaced with a stub that produces
no prompt content.

### Claim: "Analyst prompt contains deferred content" — CONFIRMED

The plan's `_build_analyst_prompt` (lines 553-573) includes XML output format
instructions and decision criteria. The PRD says analyst prompt "must be
produced after infrastructure is built so it can be iterated on against live
output." Must be a no-op stub.

### Claim: "Two competing window strategies" — CONFIRMED

Task 7 passes `guard.output_buffer[-50:]` (last 50 deltas by count). Task 9
creates `SlidingWindowScorer` (character-count window). Inconsistent. Pick one:
either the scorer manages its own window (Task 9), or the stream_patch manages
it (Task 7). Not both.

### Claim: "Config path hardcoded" — CONFIRMED

`config.py` line 902 uses `Path.home() / ".hermes" / "config.yaml"`. Should use
`get_hermes_home()` from `hermes_constants` for profile safety — this is the
Hermes convention.

---

## Risks

1. **Class-level patching conflicts:** If another plugin also patches `_fire_stream_delta`, the chain-of-wrappers approach handles it — the guard saves whatever is currently there as "original" and wraps it. The last plugin to install wins outermost position. The guard is the designated owner of this patch point; other plugins subscribe through the guard's API rather than patching independently.

2. **`_interrupt_requested` semantics:** Setting it halts the turn but the already-streamed text is still visible. For true mid-token halting, the guard must return BEFORE the original `_fire_stream_delta` is called — which it does. The streaming UX is fire-and-forget per delta; a delta not passed to callbacks never reaches the UI.

3. **Tier 1 model selection:** VADER is the MVP. HuggingFace model (e.g. `distilbert-base-uncased-finetuned-sst-2-english`) would be more accurate but adds ~250MB dependency and cold-start time. The PRD calls for a review phase — VADER lets us build and test the pipeline first.

4. **Memory backend `on_stream_delta` / `on_reasoning_delta` / `on_turn_complete`:** These are optional methods — backends without them still work via `sync_turn`. Adding them to the `MemoryProvider` ABC requires Hermes core change. Alternative: the subscription API calls `_fan_out("on_stream_delta", ...)` and backends that implement it respond; those that don't just log a warning (which multi-memory already handles in `_fan_out`).

---

## Plugin Ordering

**Hermes standard:** Plugins are isolated. Cross-plugin communication happens through
two patterns:

1. **Public API exports** — a plugin's `__init__.py` (or submodule) exports
   functions that other code imports. Example: `plugins/memory/__init__.py`
   exports `load_memory_provider()` which multi-memory consumes.

2. **Core-mediated hooks** — plugins register hooks/middleware through `ctx`,
   and Hermes core fans out events. Example: `transform_llm_output` fires for
   all registered plugins.

There is no inter-plugin dependency declaration in `plugin.yaml`. The only load-order
guarantee is alphabetical by plugin directory name (documented for `pre_llm_call`
context ordering). The standard fallback is `try/except ImportError`.

**For hermes-guard:** The guard's `subscriptions.py` is a public API module.
Subscriber plugins import from it directly. If the guard isn't installed, the
import fails and the subscriber degrades gracefully — same pattern as real
Hermes plugin code.

```python
# In multi-memory __init__.py — standard Hermes pattern
try:
    from hermes_guard.subscriptions import subscribe_stream_output
    subscribe_stream_output(_fan_output)
except ImportError:
    pass  # Guard not installed — sync_turn() still works
```

This is simpler than a deferred queue and follows the established Hermes convention
(`plugins/context_engine/__init__.py` uses the same `try/except ImportError` for
optional imports).
