"""Multi-memory plugin for Hermes Agent — fan out lifecycle calls to
multiple memory providers (Mnemosyne, Mem0, Holographic, Honcho,
OpenViking, Hindsight, RetainDB, ByteRover, Supermemory).

Usage
-----
Enable in config.yaml::

    memory:
      provider: multi
      multi:
        backends:
          mnemosyne: {}
          holographic: {}
          openviking: {}
          hindsight: {}

Or use the INVESTIGATION-C canonical::

    memory:
      providers:
        - "mnemosyne"
        - "holographic"
        - "openviking"
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Any

import yaml

try:
    from tools.registry import tool_error
except ImportError:
    def tool_error(msg: str) -> str:
        """Standalone fallback when Hermes tools.registry is unavailable."""
        return f"[multi-memory] ERROR: {msg}"

try:
    from agent.memory_provider import MemoryProvider
except ImportError:
    # Standalone / testing: provide a minimal base class matching the ABC
    import abc
    class MemoryProvider(abc.ABC):  # type: ignore[no-redef]
        """Stub base class for standalone testing outside Hermes."""

        name: str = ""
        @abc.abstractmethod
        def is_available(self) -> bool: ...
        @abc.abstractmethod
        def initialize(self, session_id: str, **kwargs) -> None: ...
        @abc.abstractmethod
        def get_tool_schemas(self) -> list[dict]: ...
        @abc.abstractmethod
        def handle_tool_call(self, tool_name: str, args: dict, **kwargs) -> str: ...
        def shutdown(self) -> None: pass
        def system_prompt_block(self) -> str: return ""
        def prefetch(self, query: str, **kwargs) -> str: return ""
        def queue_prefetch(self, query: str, **kwargs) -> None: pass
        def sync_turn(self, user_content: str, assistant_content: str, **kwargs) -> None: pass
        def on_turn_start(self, turn_number: int = 0, message: str = "", **kwargs: Any) -> None: pass
        def on_session_end(self, messages: list[dict]) -> None: pass
        def on_session_switch(self, new_session_id: str = "", *, parent_session_id: str = "", reset: bool = False, **kwargs: Any) -> None: pass
        def on_memory_write(self, action: str, target: str, content: str, metadata: dict[str, Any] | None = None) -> None: pass
        def on_delegation(self, task: str = "", result: str = "", *, child_session_id: str = "", **kwargs: Any) -> None: pass
        def on_pre_compress(self, messages: list[dict]) -> str: return ""
from .adapters import (
    _SubProviderAdapter,
    _GenericAdapter,
    _MnemosyneAdapter,
    _Mem0Adapter,
    _HolographicAdapter,
    _HonchoAdapter,
    _OpenVikingAdapter,
    _HindsightAdapter,
    _RetainDBAdapter,
    _ByteRoverAdapter,
    _SupermemoryAdapter,
)
from .budget import ToolBudgetWarning
from .validate import NamespaceValidator
from .health import HealthTracker

__all__ = [
    "MultiMemoryProvider",
    "register",
]

logger = logging.getLogger(__name__)

_SUB_CLASSES = (
    _MnemosyneAdapter,
    _Mem0Adapter,
    _HolographicAdapter,
    _HonchoAdapter,
    _OpenVikingAdapter,
    _HindsightAdapter,
    _RetainDBAdapter,
    _ByteRoverAdapter,
    _SupermemoryAdapter,
)


def _is_disabled(value: Any) -> bool:
    """Return True if a config value means 'this backend is disabled'."""
    return value is False or value is None or value in (0, "0", "false", "False", "no")


def register(ctx) -> None:
    """Entry point — called by Hermes plugin loader via _ProviderCollector."""
    ctx.register_memory_provider(MultiMemoryProvider())


class MultiMemoryProvider(MemoryProvider):
    """Hermes MemoryProvider that fans every lifecycle call across active sub-providers.

    Hermes core loads this as a single provider with ``name="multi"``.
    All actual memory operations are delegated to the active sub-providers.
    No core patches are required — the ``register(ctx)`` contract + ABC are
    sufficient for this to sit alongside any other ``MemoryProvider`` subclass
    in Hermes's builtin registry.

    Thread-safe: all lifecycle dispatch and sub-list access are protected
    by ``_lock`` (``threading.RLock``).  This matters in gateway mode where
    multiple concurrent requests may invoke lifecycle hooks simultaneously.
    """

    def __init__(self) -> None:
        self._subs: list[_SubProviderAdapter] = []
        self._tool_budget = ToolBudgetWarning()
        self._health = HealthTracker()
        self._lock = threading.RLock()
        self._load_config()
        self._validate_namespaces()

    def __repr__(self) -> str:
        with self._lock:
            names = [s.name for s in self._subs]
        return f"MultiMemoryProvider(backends={names})"

    def _load_config(self) -> None:
        """Read config.yaml and populate sub-adapters."""
        try:
            hermes_home = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
            cfg_path = os.path.join(hermes_home, "config.yaml")
            with open(cfg_path) as f:
                cfg = yaml.safe_load(f) or {}
            if not isinstance(cfg, dict):
                logger.warning("[multi-memory] config.yaml is not a dict — ignoring")
                return
            candidates = _load_backends_from_config(cfg)
            # Validate schemas BEFORE accepting — a broken backend must
            # NOT be registered (matches fork's schema-validation-before-
            # registration pattern from memory_manager.py).
            validated = []
            for adapter in candidates:
                try:
                    schemas = adapter.get_tool_schemas()
                    validated.append(adapter)
                    logger.info(
                        "[multi-memory] %s validated (%d tools)", adapter.name, len(schemas)
                    )
                except Exception as exc:
                    logger.warning(
                        "[multi-memory] %s failed schema validation — NOT registered: %s",
                        adapter.name, exc,
                    )
                    self._health.record_failure(adapter.name)
            self._subs = validated
            logger.info(
                "[multi-memory] loaded %d backends: %s",
                len(self._subs), [s.name for s in self._subs]
            )
        except Exception as exc:
            logger.warning("[multi-memory] config load failed: %s", exc)

    def _validate_namespaces(self) -> None:
        """Check all adapter PREFIX values are non-empty."""
        validator = NamespaceValidator(list(_SUB_CLASSES))
        validator.validate_all()

    # ─── Snapshot helper ───────────────────────────────────────────────────

    def _snapshot(self) -> list[_SubProviderAdapter]:
        """Return a thread-safe snapshot of active sub-providers."""
        with self._lock:
            return list(self._subs)

    # ─── 3 required abstract methods ────────────────────────────────────────

    @property
    def name(self) -> str:
        return "multi"

    @property
    def providers(self) -> list[str]:
        """Return names of all active sub-providers."""
        with self._lock:
            return [s.name for s in self._subs]

    def is_available(self) -> bool:
        return bool(self._subs)

    def initialize(self, session_id: str, **kwargs: Any) -> None:
        for sub in self._subs:
            if self._health.is_open(sub.name):
                logger.warning("[multi-memory] %s initialize() skipped (circuit open)", sub.name)
                continue
            try:
                sub.initialize(session_id=session_id, **kwargs)
                self._health.record_success(sub.name)
            except Exception as exc:
                self._health.record_failure(sub.name)
                logger.warning(
                    "[multi-memory] %s initialize() failed (%s)", sub.name, exc
                )

    def get_tool_schemas(self) -> list[dict]:
        """Merge schemas: first-seen wins by tool name."""
        with self._lock:
            schemas, seen = [], set()
            for sub in self._subs:
                try:
                    sub_schemas = sub.get_tool_schemas()
                except Exception as exc:
                    logger.warning(
                        "[multi-memory] %s get_tool_schemas() failed: %s — skipping",
                        sub.name, exc,
                    )
                    self._health.record_failure(sub.name)
                    continue
                for raw in sub_schemas:
                    name = raw.get("name", "")
                    if name and name not in seen:
                        schemas.append(raw)
                        seen.add(name)
            self._tool_budget.check(schemas)
            return schemas

    def handle_tool_call(self, tool_name: str, args: dict, **kwargs: Any) -> str:
        subs = self._snapshot()
        # Match by adapter PREFIX (not sub.name) — handles cases where
        # the config key differs from the tool prefix (e.g. ByteRover: brv_).
        for sub in subs:
            pfx = getattr(type(sub), 'PREFIX', '') or sub.name
            if tool_name.startswith(f"{pfx}_"):
                return sub.handle_tool_call(tool_name, args, **kwargs)
        # Fallback: try all subs without prefix match
        errors = []
        for sub in subs:
            try:
                return sub.handle_tool_call(tool_name, args, **kwargs)
            except Exception as exc:
                errors.append(f"{sub.name}: {exc}")
                logger.warning(
                    "[multi-memory] fallback %s for '%s': %s",
                    sub.name, tool_name, exc,
                )
        return tool_error(f"No sub-provider handles tool '{tool_name}' — tried: {'; '.join(errors)}")

    # ─── Runtime sub-provider management ──────────────────────────────────

    def get_provider(self, name: str) -> _SubProviderAdapter | None:
        """Return a sub-provider by name, or None if not found."""
        with self._lock:
            for sub in self._subs:
                if sub.name == name:
                    return sub
        return None

    def add_provider(self, adapter: _SubProviderAdapter) -> bool:
        """Add a sub-provider at runtime. Returns True if added, False if duplicate."""
        # Validate schemas before accepting (fork pattern)
        try:
            schemas = adapter.get_tool_schemas()
        except Exception as exc:
            logger.warning(
                "[multi-memory] add_provider: '%s' failed schema validation — rejected: %s",
                adapter.name, exc,
            )
            return False
        with self._lock:
            if any(s.name == adapter.name for s in self._subs):
                logger.warning("[multi-memory] add_provider: '%s' already active", adapter.name)
                return False
            self._subs.append(adapter)
            self._health.reset(adapter.name)
        logger.info(
            "[multi-memory] added provider '%s' (%d tools)", adapter.name, len(schemas)
        )
        return True

    def remove_provider(self, name: str) -> bool:
        """Shutdown and remove a sub-provider by name. Returns True if removed."""
        with self._lock:
            target = None
            remaining = []
            for sub in self._subs:
                if sub.name == name:
                    target = sub
                else:
                    remaining.append(sub)
            if target is None:
                logger.warning("[multi-memory] remove_provider: '%s' not found", name)
                return False
            self._subs = remaining
        # Shutdown outside lock
        _close_or_shutdown(target, name)
        self._health.reset(name)
        logger.info("[multi-memory] removed provider '%s'", name)
        return True

    # ─── Tool introspection ───────────────────────────────────────────────

    def get_all_tool_names(self) -> set[str]:
        """Return the set of all tool names from active sub-providers."""
        return {s["name"] for s in self.get_tool_schemas()}

    def has_tool(self, tool_name: str) -> bool:
        """Return True if any active sub-provider handles this tool."""
        return tool_name in self.get_all_tool_names()

    def health_summary(self) -> dict[str, str]:
        """Return {backend_name: 'ok' | 'circuit_open'} for all active subs."""
        with self._lock:
            return {
                sub.name: ("circuit_open" if self._health.is_open(sub.name) else "ok")
                for sub in self._subs
            }

    # ─── Optional hooks (pass-through to all active subs) ────────────────

    def shutdown(self) -> None:
        subs = self._snapshot()
        for sub in reversed(subs):
            _close_or_shutdown(sub, sub.name)
        # Clear subs so post-shutdown calls don't hit dead delegates
        with self._lock:
            self._subs.clear()

    def system_prompt_block(self) -> str:
        parts = [b for s in self._snapshot() if (b := s.system_prompt_block())]
        return "\n\n".join(parts) if parts else ""

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        parts = []
        for sub in self._snapshot():
            if self._health.is_open(sub.name):
                continue
            try:
                r = sub.prefetch(query, session_id=session_id)
                if r:
                    parts.append(f"[{sub.name}] {r}")
                self._health.record_success(sub.name)
            except Exception as exc:
                self._health.record_failure(sub.name)
                logger.warning("[multi-memory] prefetch %s: %s", sub.name, exc)
        return "\n\n".join(parts)

    def queue_prefetch(self, query: str, *, session_id: str = "") -> None:
        for sub in self._snapshot():
            if self._health.is_open(sub.name):
                continue
            try:
                sub.queue_prefetch(query, session_id=session_id)
                self._health.record_success(sub.name)
            except Exception as exc:
                self._health.record_failure(sub.name)
                logger.warning("[multi-memory] queue_prefetch %s: %s", sub.name, exc)

    def sync_turn(self, user_content: str, assistant_content: str, *, session_id: str = "", **kwargs: Any) -> None:
        messages = kwargs.get("messages")
        for sub in self._snapshot():
            if self._health.is_open(sub.name):
                continue
            try:
                sub.sync_turn(user_content, assistant_content, session_id=session_id, messages=messages)
                self._health.record_success(sub.name)
            except Exception as exc:
                self._health.record_failure(sub.name)
                logger.warning("[multi-memory] sync_turn %s: %s", sub.name, exc)

    def on_turn_start(self, turn_number: int = 0, message: str = "", **kwargs: Any) -> None:
        for sub in self._snapshot():
            if self._health.is_open(sub.name):
                continue
            try:
                sub.on_turn_start(turn_number, message, **kwargs)
                self._health.record_success(sub.name)
            except Exception as exc:
                self._health.record_failure(sub.name)
                logger.warning("[multi-memory] on_turn_start %s: %s", sub.name, exc)

    def on_session_end(self, messages: list[dict]) -> None:
        for sub in self._snapshot():
            if self._health.is_open(sub.name):
                continue
            try:
                sub.on_session_end(messages)
                self._health.record_success(sub.name)
            except Exception as exc:
                self._health.record_failure(sub.name)
                logger.warning("[multi-memory] on_session_end %s: %s", sub.name, exc)

    def on_session_switch(self, new_session_id: str = "", *, parent_session_id: str = "", reset: bool = False, **kwargs: Any) -> None:
        if not new_session_id:
            return
        for sub in self._snapshot():
            if self._health.is_open(sub.name):
                continue
            try:
                sub.on_session_switch(new_session_id, parent_session_id=parent_session_id, reset=reset, **kwargs)
                self._health.record_success(sub.name)
            except Exception as exc:
                self._health.record_failure(sub.name)
                logger.warning("[multi-memory] on_session_switch %s: %s", sub.name, exc)

    def on_memory_write(self, action: str, target: str, content: str, metadata: dict[str, Any] | None = None) -> None:
        for sub in self._snapshot():
            if self._health.is_open(sub.name):
                continue
            try:
                sub.on_memory_write(action, target, content, metadata)
                self._health.record_success(sub.name)
            except Exception as exc:
                self._health.record_failure(sub.name)
                logger.warning("[multi-memory] on_memory_write %s: %s", sub.name, exc)

    def on_delegation(self, task: str = "", result: str = "", *, child_session_id: str = "", **kwargs: Any) -> None:
        for sub in self._snapshot():
            if self._health.is_open(sub.name):
                continue
            try:
                sub.on_delegation(task, result, child_session_id=child_session_id, **kwargs)
                self._health.record_success(sub.name)
            except Exception as exc:
                self._health.record_failure(sub.name)
                logger.warning("[multi-memory] on_delegation %s: %s", sub.name, exc)

    def on_pre_compress(self, messages: list[dict[str, Any]]) -> str:
        parts = []
        for sub in self._snapshot():
            if self._health.is_open(sub.name):
                continue
            try:
                r = sub.on_pre_compress(messages)
                if r:
                    parts.append(f"[{sub.name}] {r}")
                self._health.record_success(sub.name)
            except Exception as exc:
                self._health.record_failure(sub.name)
                logger.warning("[multi-memory] on_pre_compress %s: %s", sub.name, exc)
        return "\n\n".join(parts) if parts else ""


# ── Helpers ────────────────────────────────────────────────────────────────

def _close_or_shutdown(sub: _SubProviderAdapter, name: str) -> None:
    """Close or shutdown a sub-provider, preferring close()."""
    try:
        close_fn = getattr(sub, 'close', None)
        if callable(close_fn):
            close_fn()
        else:
            sub.shutdown()
    except Exception as exc:
        logger.warning("[multi-memory] shutdown %s: %s", name, exc)


def _normalise_multi_config(cfg: dict | None) -> dict:
    """Return a unified backends dict from *either* config shape.

    INVESTIGATION-C canonical  -  ``providers: list[str]`` (fork format)
    PLAN spec                  -  ``multi.backends: dict[name -> enabled]``

    Both formats are accepted.  ``providers`` list wins when non-empty.
    Returns ``{}`` on absence or parse failure.
    """
    if not isinstance(cfg, dict):
        return {}
    prov_list = cfg.get("providers") or []
    if isinstance(prov_list, list) and prov_list:
        return {p: {} for p in prov_list}
    multi_cfg = cfg.get("multi") or {}
    backends = multi_cfg.get("backends") or {}
    if isinstance(backends, dict):
        return backends
    return {}


def _load_backends_from_config(config: dict) -> list[_SubProviderAdapter]:
    """Return list of instantiated _SubProviderAdapter from config.

    Accepts both INVESTIGATION-C format (``providers: list[str]``) and
    PLAN spec format (``multi.backends: dict``).  ``_normalise_multi_config``
    merges both into a single ``{key: enabled}`` dict before adapter loading.
    """
    backends: list[_SubProviderAdapter] = []
    backend_cfg = _normalise_multi_config(config.get("memory") or {})
    for key, enabled in backend_cfg.items():
        if _is_disabled(enabled):
            continue
        for cls in _SUB_CLASSES:
            if cls.CONFIG_KEY == key:
                try:
                    adapter = cls()
                    if adapter.is_available():
                        backends.append(adapter)
                    else:
                        logger.warning(
                            "[multi-memory] %s installed but not available "
                            "(missing credentials or config?)",
                            key,
                        )
                except Exception as exc:
                    logger.warning(
                        "[multi-memory] %s listed in config but failed to load: %s",
                        key, exc,
                    )
                break
        else:
            # No hardcoded adapter — try Hermes's plugin discovery
            _try_generic_backend(key, backends)
    return backends


def _try_generic_backend(name: str, backends: list[_SubProviderAdapter]) -> None:
    """Try to load a backend via Hermes's ``load_memory_provider()`` discovery.

    This enables custom/third-party backends that aren't hardcoded in the
    plugin.  Any ``MemoryProvider`` implementation dropped into
    ``plugins/memory/<name>/`` will be discovered and wrapped in a
    ``_GenericAdapter``.
    """
    try:
        from plugins.memory import load_memory_provider
        provider = load_memory_provider(name)
        if provider is None:
            logger.warning(
                "[multi-memory] backend '%s' not found in hardcoded adapters "
                "or Hermes plugin discovery — skipping", name,
            )
            return
        adapter = _GenericAdapter(provider, name)
        if adapter.is_available():
            backends.append(adapter)
            logger.info(
                "[multi-memory] '%s' loaded via plugin discovery (generic adapter)", name,
            )
        else:
            logger.warning(
                "[multi-memory] '%s' discovered but not available "
                "(missing credentials or config?)", name,
            )
    except ImportError:
        # plugins.memory not available (standalone mode)
        logger.warning(
            "[multi-memory] backend '%s' not in hardcoded adapters "
            "and plugin discovery unavailable — skipping", name,
        )
    except Exception as exc:
        logger.warning(
            "[multi-memory] backend '%s' failed during plugin discovery: %s",
            name, exc,
        )
