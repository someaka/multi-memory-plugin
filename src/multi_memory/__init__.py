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
    """

    def __init__(self) -> None:
        self._subs: list[_SubProviderAdapter] = []
        self._tool_budget = ToolBudgetWarning()
        self._health = HealthTracker()
        self._load_config()
        self._validate_namespaces()

    def _load_config(self) -> None:
        """Read config.yaml and populate sub-adapters."""
        try:
            hermes_home = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
            cfg_path = os.path.join(hermes_home, "config.yaml")
            with open(cfg_path) as f:
                cfg = yaml.safe_load(f) or {}
            self._subs = _load_backends_from_config(cfg)
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

    # ─── 3 required abstract methods ────────────────────────────────────────

    @property
    def name(self) -> str:
        return "multi"

    def is_available(self) -> bool:
        return bool(self._subs)

    def initialize(self, session_id: str, **kwargs: Any) -> None:
        for sub in self._subs:
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
        schemas, seen = [], set()
        for sub in self._subs:
            for raw in sub.get_tool_schemas():
                name = raw.get("name", "")
                if name and name not in seen:
                    schemas.append(raw)
                    seen.add(name)
        self._tool_budget.check(schemas)
        return schemas

    def handle_tool_call(self, tool_name: str, args: dict, **kwargs: Any) -> str:
        # Match by adapter PREFIX (not sub.name) — handles cases where
        # the config key differs from the tool prefix (e.g. ByteRover: brv_).
        for sub in self._subs:
            pfx = getattr(type(sub), 'PREFIX', '') or sub.name
            if tool_name.startswith(f"{pfx}_"):
                return sub.handle_tool_call(tool_name, args, **kwargs)
        # Fallback: try all subs without prefix match
        for sub in self._subs:
            try:
                return sub.handle_tool_call(tool_name, args, **kwargs)
            except Exception as exc:
                logger.debug(
                    "[multi-memory] fallback %s for '%s': %s",
                    sub.name, tool_name, exc,
                )
        return tool_error(f"No sub-provider handles tool '{tool_name}'")

    # ─── Optional hooks (pass-through to all active subs) ──

    def shutdown(self) -> None:
        for sub in reversed(self._subs):
            try:
                sub.shutdown()
                self._health.record_success(f"{sub.name}.shutdown")
            except Exception as exc:
                self._health.record_failure(f"{sub.name}.shutdown")
                logger.debug("[multi-memory] shutdown %s: %s", sub.name, exc)

    def system_prompt_block(self) -> str:
        parts = [b for s in self._subs if (b := s.system_prompt_block())]
        return "\n\n".join(parts) if parts else ""

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        parts = []
        for sub in self._subs:
            try:
                r = sub.prefetch(query, session_id=session_id)
                if r:
                    parts.append(f"[{sub.name}] {r}")
            except Exception as exc:
                self._health.record_failure(sub.name)
                logger.debug("[multi-memory] prefetch %s: %s", sub.name, exc)
        return "\n\n".join(parts)

    def queue_prefetch(self, query: str, *, session_id: str = "") -> None:
        for sub in self._subs:
            if self._health.is_open(sub.name):
                continue
            try:
                sub.queue_prefetch(query, session_id=session_id)
                self._health.record_success(sub.name)
            except Exception as exc:
                self._health.record_failure(sub.name)
                logger.debug("[multi-memory] queue_prefetch %s: %s", sub.name, exc)

    def sync_turn(self, user_content: str, assistant_content: str, *, session_id: str = "") -> None:
        for sub in self._subs:
            if self._health.is_open(sub.name):
                continue
            try:
                sub.sync_turn(user_content, assistant_content, session_id=session_id)
                self._health.record_success(sub.name)
            except Exception as exc:
                self._health.record_failure(sub.name)
                logger.debug("[multi-memory] sync_turn %s: %s", sub.name, exc)

    def on_turn_start(self, turn_number: int = 0, message: str = "", **kwargs: Any) -> None:
        for sub in self._subs:
            if self._health.is_open(sub.name):
                continue
            try:
                sub.on_turn_start(turn_number, message, **kwargs)
                self._health.record_success(sub.name)
            except Exception as exc:
                self._health.record_failure(sub.name)
                logger.debug("[multi-memory] on_turn_start %s: %s", sub.name, exc)

    def on_session_end(self, messages: list[dict]) -> None:
        for sub in self._subs:
            if self._health.is_open(sub.name):
                continue
            try:
                sub.on_session_end(messages)
                self._health.record_success(sub.name)
            except Exception as exc:
                self._health.record_failure(sub.name)
                logger.debug("[multi-memory] on_session_end %s: %s", sub.name, exc)

    def on_session_switch(self, new_session_id: str = "", *, parent_session_id: str = "", reset: bool = False, **kwargs: Any) -> None:
        for sub in self._subs:
            if self._health.is_open(sub.name):
                continue
            try:
                sub.on_session_switch(new_session_id, parent_session_id=parent_session_id, reset=reset, **kwargs)
                self._health.record_success(sub.name)
            except Exception as exc:
                self._health.record_failure(sub.name)
                logger.debug("[multi-memory] on_session_switch %s: %s", sub.name, exc)

    def on_memory_write(self, action: str, target: str, content: str, metadata: dict[str, Any] | None = None) -> None:
        for sub in self._subs:
            if self._health.is_open(sub.name):
                continue
            try:
                sub.on_memory_write(action, target, content, metadata)
                self._health.record_success(sub.name)
            except Exception as exc:
                self._health.record_failure(sub.name)
                logger.debug("[multi-memory] on_memory_write %s: %s", sub.name, exc)

    def on_delegation(self, task: str = "", result: str = "", *, child_session_id: str = "", **kwargs: Any) -> None:
        for sub in self._subs:
            if self._health.is_open(sub.name):
                continue
            try:
                sub.on_delegation(task, result, child_session_id=child_session_id, **kwargs)
                self._health.record_success(sub.name)
            except Exception as exc:
                self._health.record_failure(sub.name)
                logger.debug("[multi-memory] on_delegation %s: %s", sub.name, exc)

    def on_pre_compress(self, messages: list[dict[str, Any]]) -> str:
        parts = []
        for sub in self._subs:
            if self._health.is_open(sub.name):
                continue
            try:
                r = sub.on_pre_compress(messages)
                if r:
                    parts.append(f"[{sub.name}] {r}")
                self._health.record_success(sub.name)
            except Exception as exc:
                self._health.record_failure(sub.name)
                logger.debug("[multi-memory] on_pre_compress %s: %s", sub.name, exc)
        return "\n\n".join(parts) if parts else ""


def _normalise_multi_config(cfg: dict | None) -> dict:
    """Return a unified backends dict from *either* config shape.

    INVESTIGATION-C canonical  -  ``providers: list[str]`` (fork format)
    PLAN spec                  -  ``multi.backends: dict[name -> enabled]``

    Both formats are accepted.  ``providers`` list wins when non-empty.
    Returns ``{}`` on absence or parse failure.
    """
    cfg = cfg or {}
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
    backends: list = []
    backend_cfg = _normalise_multi_config(config.get("memory") or {})
    for key, enabled in backend_cfg.items():
        # Backend is disabled only if explicitly False/None/0/"no",
        # not for empty dict {} which means "enabled with no extra config"
        if enabled is False or enabled is None or enabled in (0, "0", "false", "False", "no"):  # also accept "False" (capital F, still string) since Python reads it from YAML
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
            logger.warning("[multi-memory] unknown backend '%s'  skipping", key)
    return backends
