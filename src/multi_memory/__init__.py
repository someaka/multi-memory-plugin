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
import threading
from typing import Any

import yaml

try:
    from tools.registry import tool_error
except ImportError:  # pragma: no cover — standalone fallback

    def tool_error(msg: str) -> str:
        """Standalone fallback when Hermes tools.registry is unavailable."""
        return f"[multi-memory] ERROR: {msg}"


try:
    from agent.memory_provider import MemoryProvider
except ImportError:  # pragma: no cover — standalone stub
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
        def shutdown(self) -> None:  # noqa: B027
            pass

        def system_prompt_block(self) -> str:
            return ""

        def prefetch(self, query: str, **kwargs) -> str:
            return ""

        def queue_prefetch(self, query: str, **kwargs) -> None:  # noqa: B027
            pass

        def sync_turn(self, user_content: str, assistant_content: str, **kwargs) -> None:  # noqa: B027
            pass

        def on_turn_start(  # noqa: B027
            self,
            turn_number: int = 0,
            message: str = "",
            **kwargs: Any,
        ) -> None:
            pass

        def on_session_end(self, messages: list[dict]) -> None:  # noqa: B027
            pass

        def on_session_switch(  # noqa: B027
            self,
            new_session_id: str = "",
            *,
            parent_session_id: str = "",
            reset: bool = False,
            **kwargs: Any,
        ) -> None:
            pass

        def on_memory_write(  # noqa: B027
            self,
            action: str,
            target: str,
            content: str,
            metadata: dict[str, Any] | None = None,
        ) -> None:
            pass

        def on_delegation(  # noqa: B027
            self,
            task: str = "",
            result: str = "",
            *,
            child_session_id: str = "",
            **kwargs: Any,
        ) -> None:
            pass

        def on_pre_compress(self, messages: list[dict]) -> str:
            return ""


from .adapters import (
    _ByteRoverAdapter,
    _GenericAdapter,
    _HindsightAdapter,
    _HolographicAdapter,
    _HonchoAdapter,
    _Mem0Adapter,
    _MnemosyneAdapter,
    _OpenVikingAdapter,
    _RetainDBAdapter,
    _SubProviderAdapter,
    _SupermemoryAdapter,
)
from .budget import ToolBudgetWarning
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

# Validate all adapter PREFIX attributes at import time
from .validate import NamespaceValidator  # noqa: E402, PLC0415

_validator = NamespaceValidator(list(_SUB_CLASSES))
_prefix_warnings = _validator.validate_all()
if _prefix_warnings:
    logger.warning(
        "[multi-memory] %d adapter(s) have empty PREFIX — tool name collisions possible",
        len(_prefix_warnings),
    )
del _validator, _prefix_warnings  # cleanup module namespace


def _is_disabled(value: Any) -> bool:
    """Return True if a config value means 'this backend is disabled'.

    Handles YAML falsey values (False, None, 0, "false", "no"),
    plus an empty-string or empty-dict that might appear from
    ``hermes multi add`` setting ``backend: {}`` vs manual edits.
    """
    if value is False or value is None:
        return True
    if isinstance(value, str):
        return value.strip() in ("", "0", "false", "False", "no")
    return bool(isinstance(value, int) and value == 0)


def register(ctx) -> None:
    """Entry point — called by Hermes plugin loader.

    Registers the MultiMemoryProvider with the memory system **and**
    the ``hermes multi`` CLI commands with the general plugin system.

    Two separate callers may invoke this function:

    * **Memory scanner** (``_ProviderCollector``) — has
      ``register_memory_provider``.  Registers the provider so it
      becomes available as ``memory.provider: multi``.
    * **General scanner** (``PluginContext``) — has
      ``register_cli_command`` but NOT ``register_memory_provider``.
      In current Hermes the general scanner skips memory plugins
      (kind="exclusive") so this path is never reached, but the
      capability check keeps the code safe in case scanning changes.

    The provider is only instantiated when the memory scanner is
    the caller, avoiding unnecessary config reads and adapter
    creation during general plugin discovery.
    """
    if hasattr(ctx, "register_memory_provider"):
        provider = MultiMemoryProvider()
        ctx.register_memory_provider(provider)

    if hasattr(ctx, "register_cli_command"):
        from .cli import multi_command, register_cli  # noqa: PLC0415

        ctx.register_cli_command(
            name="multi",
            help="Manage multi-memory backends (status, list, add, remove)",
            setup_fn=register_cli,
            handler_fn=multi_command,
            description="Multi-memory backend management CLI",
        )


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
        self._cached_schemas: list[dict] | None = None  # invalidated on mutation
        self._load_config()
        self._apply_budget_threshold()

    def __repr__(self) -> str:
        with self._lock:
            names = [s.name for s in self._subs]
        return f"MultiMemoryProvider(backends={names})"

    def format_config_display(self, config: dict) -> list[tuple[str, str]]:
        """Return clean (key, display_value) pairs for hermes memory status.

        Overrides the default raw-dict display so backends show as
        ``backends: mnemosyne, openviking`` instead of
        ``backends: {'mnemosyne': {}, 'openviking': {}}``.
        """
        multi_cfg = config.get("multi", {})
        backends = multi_cfg.get("backends", {})
        if backends:
            items = ", ".join(k if v in ({}, True) else f"{k}({v})" for k, v in backends.items())
            return [("backends", items)]
        providers = config.get("providers", [])
        if providers:
            return [("providers", ", ".join(providers))]
        return []

    def _load_config(self) -> None:
        """Read config.yaml and populate sub-adapters.

        Uses a recursion guard: ``_load_config`` may be re-entered
        when ``load_memory_provider`` is called during CLI status
        commands, because Hermes resolves the active provider from
        config each time a provider is loaded.
        """
        if getattr(self, "_loading", False):
            return
        self._loading = True  # noqa: SIM115
        try:
            self.__load_config_impl()
        finally:
            self._loading = False

    def __load_config_impl(self) -> None:
        from .config import _get_config_path  # noqa: PLC0415

        cfg_path = _get_config_path()
        try:
            with open(cfg_path) as f:
                cfg = yaml.safe_load(f) or {}
        except FileNotFoundError:
            logger.debug("[multi-memory] config not found at %s", cfg_path)
            return
        except (PermissionError, IsADirectoryError, yaml.YAMLError) as exc:
            logger.warning("[multi-memory] failed to read config at %s: %s", cfg_path, exc)
            return
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
                logger.info("[multi-memory] %s validated (%d tools)", adapter.name, len(schemas))
            except Exception as exc:  # noqa: PERF203
                logger.warning(
                    "[multi-memory] %s failed schema validation — NOT registered: %s",
                    adapter.name,
                    exc,
                )
                self._health.record_failure(adapter.name)
        self._subs = validated
        logger.info(
            "[multi-memory] loaded %d backends: %s",
            len(self._subs),
            [s.name for s in self._subs],
        )

    # ─── Snapshot helper ───────────────────────────────────────────────────

    def _apply_budget_threshold(self) -> None:
        """Read tool_budget_threshold from config and apply to budget checker."""
        from .config import _get_config_path  # noqa: PLC0415

        try:
            with open(_get_config_path()) as f:
                cfg = yaml.safe_load(f) or {}
        except Exception as exc:
            logger.debug("[multi-memory] _apply_budget_threshold failed: %s", exc)
            return
        memory_cfg = cfg.get("memory", {}) if isinstance(cfg, dict) else {}
        multi_cfg = memory_cfg.get("multi", {}) if isinstance(memory_cfg, dict) else {}
        threshold = multi_cfg.get("tool_budget_threshold")
        if isinstance(threshold, int) and threshold > 0:
            self._tool_budget._threshold = threshold

    def _snapshot(self) -> list[_SubProviderAdapter]:
        """Return a thread-safe snapshot of active sub-providers."""
        with self._lock:
            return list(self._subs)

    def _fan_out(
        self, method: str, *args: Any, **kwargs: Any
    ) -> list[tuple[_SubProviderAdapter, Any]]:
        """Call *method* on every active sub, returning [(sub, result), ...].

        Subs with circuit open are skipped.  Exceptions are caught and logged;
        results from failing subs are excluded from the return list.

        This eliminates the repeated fire-and-forget / collect pattern that
        every lifecycle hook previously duplicated.
        """
        results: list[tuple[_SubProviderAdapter, Any]] = []
        for sub in self._snapshot():
            fn = getattr(sub, method, None)
            if not callable(fn):
                logger.warning(
                    "[multi-memory] %s has no method '%s' — skipping",
                    sub.name,
                    method,
                )
                continue
            try:
                result = fn(*args, **kwargs)
                self._health.record_success(sub.name)
                results.append((sub, result))
            except Exception as exc:
                self._health.record_failure(sub.name)
                logger.warning(
                    "[multi-memory] %s::%s(): %s",
                    sub.name,
                    method,
                    exc,
                )
        return results

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
        return any(sub.is_available() for sub in self._snapshot())

    def initialize(self, session_id: str, **kwargs: Any) -> None:
        self._fan_out("initialize", session_id=session_id, **kwargs)

    def get_tool_schemas(self) -> list[dict]:
        """Merge schemas: first-seen wins by tool name.

        Results are cached and invalidated on add/remove/reload.
        """
        if self._cached_schemas is not None:
            return self._cached_schemas
        subs = self._snapshot()
        schemas, seen = [], set()
        for sub in subs:
            try:
                sub_schemas = sub.get_tool_schemas()
                self._health.record_success(sub.name)
            except Exception as exc:
                logger.warning(
                    "[multi-memory] %s get_tool_schemas() failed: %s — skipping",
                    sub.name,
                    exc,
                )
                self._health.record_failure(sub.name)
                continue
            for raw in sub_schemas:
                name = raw.get("name", "")
                if name and name not in seen:
                    schemas.append(raw)
                    seen.add(name)
        self._tool_budget.check(schemas)
        self._cached_schemas = schemas
        return schemas

    def _invalidate_schema_cache(self) -> None:
        """Clear cached tool schemas — called after add/remove/reload."""
        self._cached_schemas = None

    def handle_tool_call(self, tool_name: str, args: dict, **kwargs: Any) -> str:
        subs = self._snapshot()
        # Match by adapter PREFIX (not sub.name) — handles cases where
        # the config key differs from the tool prefix (e.g. ByteRover: brv_).
        for sub in subs:
            pfx = getattr(type(sub), "PREFIX", "") or sub.name
            if tool_name.startswith(f"{pfx}_"):
                return sub.handle_tool_call(tool_name, args, **kwargs)
        # Fallback: try all subs without prefix match
        errors = []
        for sub in subs:
            try:
                return sub.handle_tool_call(tool_name, args, **kwargs)
            except Exception as exc:  # noqa: PERF203
                errors.append(f"{sub.name}: {exc}")
                logger.warning(
                    "[multi-memory] fallback %s for '%s': %s",
                    sub.name,
                    tool_name,
                    exc,
                )
        return tool_error(
            f"No sub-provider handles tool '{tool_name}' — tried: {'; '.join(errors)}"
        )

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
                adapter.name,
                exc,
            )
            return False
        with self._lock:
            if any(s.name == adapter.name for s in self._subs):
                logger.warning("[multi-memory] add_provider: '%s' already active", adapter.name)
                return False
            self._subs.append(adapter)
            self._invalidate_schema_cache()
            self._health.reset(adapter.name)
        logger.info("[multi-memory] added provider '%s' (%d tools)", adapter.name, len(schemas))
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
            self._invalidate_schema_cache()
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

    def health_summary(self) -> dict[str, int]:
        """Return {backend_name: consecutive_failure_count} for all active subs."""
        with self._lock:
            return {
                sub.name: self._health.consecutive_failures(sub.name)
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
        parts = [r for _, r in self._fan_out("system_prompt_block") if r]
        return "\n\n".join(parts) if parts else ""

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        results = self._fan_out("prefetch", query, session_id=session_id)
        parts = [f"[{sub.name}] {r}" for sub, r in results if r]
        return "\n\n".join(parts)

    def queue_prefetch(self, query: str, *, session_id: str = "") -> None:
        self._fan_out("queue_prefetch", query, session_id=session_id)

    def sync_turn(
        self, user_content: str, assistant_content: str, *, session_id: str = "", **kwargs: Any
    ) -> None:
        messages = kwargs.get("messages")
        self._fan_out(
            "sync_turn", user_content, assistant_content, session_id=session_id, messages=messages
        )

    def on_turn_start(self, turn_number: int = 0, message: str = "", **kwargs: Any) -> None:
        self._fan_out("on_turn_start", turn_number, message, **kwargs)

    def on_session_end(self, messages: list[dict]) -> None:
        self._fan_out("on_session_end", messages)

    def on_session_switch(
        self,
        new_session_id: str = "",
        *,
        parent_session_id: str = "",
        reset: bool = False,
        **kwargs: Any,
    ) -> None:
        if not new_session_id:
            return
        self._fan_out(
            "on_session_switch",
            new_session_id,
            parent_session_id=parent_session_id,
            reset=reset,
            **kwargs,
        )

    def on_memory_write(
        self, action: str, target: str, content: str, metadata: dict[str, Any] | None = None
    ) -> None:
        self._fan_out("on_memory_write", action, target, content, metadata)

    def on_delegation(
        self, task: str = "", result: str = "", *, child_session_id: str = "", **kwargs: Any
    ) -> None:
        self._fan_out("on_delegation", task, result, child_session_id=child_session_id, **kwargs)

    def on_pre_compress(self, messages: list[dict[str, Any]]) -> str:
        results = self._fan_out("on_pre_compress", messages)
        parts = [f"[{sub.name}] {r}" for sub, r in results if r]
        return "\n\n".join(parts) if parts else ""


# ── Helpers ────────────────────────────────────────────────────────────────


def _close_or_shutdown(sub: _SubProviderAdapter, name: str, timeout: float = 10.0) -> None:
    """Close or shutdown a sub-provider, preferring close().

    Runs in a separate thread with a *timeout* (default 10s) to prevent
    a hung sub-provider from blocking shutdown indefinitely.
    """
    import concurrent.futures  # noqa: PLC0415

    def _do_close() -> None:
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
        logger.warning(
            "[multi-memory] shutdown %s timed out after %.0fs — abandoned",
            name,
            timeout,
        )
    except Exception as exc:
        logger.warning("[multi-memory] shutdown %s: %s", name, exc)


def _normalise_multi_config(cfg: dict | None) -> dict:
    """Return a unified backends dict from *either* config shape.

    INVESTIGATION-C canonical  -  ``providers: list[str]`` (fork format)
    PLAN spec                  -  ``multi.backends: dict[name -> enabled]``

    Both formats are accepted.  ``multi.backends`` dict is canonical;
    ``providers`` list is a legacy fallback.
    Returns ``{}`` on absence or parse failure.
    """
    if not isinstance(cfg, dict):
        return {}
    multi_cfg = cfg.get("multi") or {}
    backends = multi_cfg.get("backends") or {}
    if isinstance(backends, dict) and backends:
        return backends
    providers = cfg.get("providers")
    if isinstance(providers, list) and providers:
        return {p: {} for p in providers}
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
            if key == cls.CONFIG_KEY:
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
                        key,
                        exc,
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
        from plugins.memory import load_memory_provider  # noqa: PLC0415

        provider = load_memory_provider(name)
        if provider is None:
            logger.warning(
                "[multi-memory] backend '%s' not found in hardcoded adapters "
                "or Hermes plugin discovery — skipping",
                name,
            )
            return
        adapter = _GenericAdapter(provider, name)
        if adapter.is_available():
            backends.append(adapter)
            logger.info(
                "[multi-memory] '%s' loaded via plugin discovery (generic adapter)",
                name,
            )
        else:
            logger.warning(
                "[multi-memory] '%s' discovered but not available (missing credentials or config?)",
                name,
            )
    except ImportError:
        # plugins.memory not available (standalone mode)
        logger.warning(
            "[multi-memory] backend '%s' not in hardcoded adapters "
            "and plugin discovery unavailable — skipping",
            name,
        )
    except Exception as exc:
        logger.warning(
            "[multi-memory] backend '%s' failed during plugin discovery: %s",
            name,
            exc,
        )


_loading_config = False
