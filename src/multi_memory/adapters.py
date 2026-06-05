"""Adapter layer that wraps Hermes MemoryProvider subclasses into a common interface.

Each known backend (Mnemosyne, Mem0, Holographic, Honcho, OpenViking,
Hindsight, RetainDB, ByteRover, Supermemory) has a thin ``_SubProviderAdapter``
subclass that delegates lifecycle calls to the real provider while prefixing
tool names to avoid collisions.

Usage
-----
Adapters are not instantiated directly — the ``MultiMemoryProvider``
in ``__init__.py`` discovers and instantiates them from config.
"""

from __future__ import annotations

import importlib
import inspect
import logging
from importlib.util import find_spec
from typing import Any

logger = logging.getLogger(__name__)


def _try_import(module: str, cls: str) -> type | None:
    """Return a provider class or None if module absent / cannot import."""
    try:
        if find_spec(module) is None:
            return None
    except (ModuleNotFoundError, ValueError):
        # ModuleNotFoundError: parent package missing (e.g. "plugins" not installed)
        # ValueError: module name is invalid
        return None
    try:
        mod = importlib.import_module(module)
        return getattr(mod, cls, None)
    except Exception as exc:
        logger.debug(
            "[multi-memory] _try_import(%s.%s) failed: %s",
            module,
            cls,
            exc,
        )
        return None


def _renorm_schemas(raw: list[dict], prefix: str) -> list[dict]:
    """Strip existing prefix, re-add — guarantees exactly one prefix.

    Handles backends that self-prefix (``holographic_store``) and
    backends that don't (``fact_store``) uniformly.  Single-pass O(n).
    """
    pfx = f"{prefix}_"
    result = []
    for s in raw:
        name = s["name"]
        if name.startswith(pfx):
            name = name[len(pfx) :]
        result.append({**s, "name": f"{prefix}_{name}"})
    return result


_MIN_POS_ARGS_FOR_METADATA = 4  # on_memory_write(action, target, content, metadata)


class _SubProviderAdapter:
    """Base class for all sub-provider adapters — thin delegation wrapper."""

    CONFIG_KEY: str = ""
    MODULE: str = ""
    CLASS: str = ""
    PREFIX: str = ""  # tool name prefix = config-key (full name avoids collision)

    def __init__(self, **kwargs: Any):
        real_cls = _try_import(self.MODULE, self.CLASS)
        if real_cls is None:
            raise RuntimeError(
                f"[multi-memory] backend '{self.CONFIG_KEY}' not installed "
                f"(pip install {self.CONFIG_KEY!r})"
            )
        self._delegate = real_cls()
        # Cache introspection results — delegate doesn't change after init
        self._cached_write_mode: str | None = None
        self._cached_accepts_messages: bool | None = None

    @property
    def name(self) -> str:
        return self._delegate.name

    def is_available(self) -> bool:
        return self._delegate.is_available()

    def initialize(self, session_id: str, **kwargs: Any) -> None:
        self._delegate.initialize(session_id=session_id, **kwargs)

    def shutdown(self) -> None:
        self._delegate.shutdown()

    def get_tool_schemas(self) -> list[dict]:
        raw = self._delegate.get_tool_schemas()
        return _renorm_schemas(raw, self.PREFIX)

    def handle_tool_call(self, tool_name: str, args: dict, **kwargs: Any) -> str:
        # Pass full name through — most backends self-prefix their tools
        # (mnemosyne_recall, mem0_search, etc.). Backends that don't
        # self-prefix (holographic) override this method.
        return self._delegate.handle_tool_call(tool_name, args, **kwargs)

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        return self._delegate.prefetch(query, session_id=session_id)

    def queue_prefetch(self, query: str, *, session_id: str = "") -> None:
        self._delegate.queue_prefetch(query, session_id=session_id)

    def sync_turn(
        self,
        user_content: str,
        assistant_content: str,
        *,
        session_id: str = "",
        messages: list[dict] | None = None,
    ) -> None:
        if messages is not None and self._sync_accepts_messages():
            self._delegate.sync_turn(
                user_content,
                assistant_content,
                session_id=session_id,
                messages=messages,
            )
        else:
            self._delegate.sync_turn(
                user_content,
                assistant_content,
                session_id=session_id,
            )

    def system_prompt_block(self) -> str:
        return self._delegate.system_prompt_block()

    def on_turn_start(self, turn_number: int = 0, message: str = "", **kwargs: Any) -> None:
        self._delegate.on_turn_start(turn_number, message, **kwargs)

    def on_session_end(self, messages: list[dict]) -> None:
        self._delegate.on_session_end(messages)

    def on_session_switch(
        self,
        new_session_id: str = "",
        *,
        parent_session_id: str = "",
        reset: bool = False,
        **kwargs: Any,
    ) -> None:
        self._delegate.on_session_switch(
            new_session_id,
            parent_session_id=parent_session_id,
            reset=reset,
            **kwargs,
        )

    def on_memory_write(
        self, action: str, target: str, content: str, metadata: dict[str, Any] | None = None
    ) -> None:
        mode = self._metadata_write_mode()
        if mode == "keyword":
            self._delegate.on_memory_write(action, target, content, metadata=dict(metadata or {}))
        elif mode == "positional":
            self._delegate.on_memory_write(action, target, content, dict(metadata or {}))
        else:
            self._delegate.on_memory_write(action, target, content)

    def on_delegation(
        self, task: str = "", result: str = "", *, child_session_id: str = "", **kwargs: Any
    ) -> None:
        self._delegate.on_delegation(
            task,
            result,
            child_session_id=child_session_id,
            **kwargs,
        )

    def on_pre_compress(self, messages: list[dict[str, Any]]) -> str:
        return self._delegate.on_pre_compress(messages)

    # -- Introspection helpers (cached) ------------------------------------

    def _metadata_write_mode(self) -> str:
        """Detect how the delegate's on_memory_write accepts metadata.

        Returns 'keyword' if it accepts metadata as keyword arg,
        'positional' if it accepts 4 positional args, or 'legacy' if
        it only accepts 3 args (no metadata).
        """
        if self._cached_write_mode is not None:
            return self._cached_write_mode
        try:
            sig = inspect.signature(self._delegate.on_memory_write)
        except (TypeError, ValueError):
            self._cached_write_mode = "keyword"
            return self._cached_write_mode
        params = list(sig.parameters.values())
        if (
            any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params)
            or "metadata" in sig.parameters
        ):
            self._cached_write_mode = "keyword"
        else:
            accepted = [
                p
                for p in params
                if p.kind
                in {
                    inspect.Parameter.POSITIONAL_ONLY,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    inspect.Parameter.KEYWORD_ONLY,
                }
            ]
            self._cached_write_mode = (
                "positional" if len(accepted) >= _MIN_POS_ARGS_FOR_METADATA else "legacy"
            )
        return self._cached_write_mode

    def _sync_accepts_messages(self) -> bool:
        """Return whether the delegate's sync_turn accepts a messages keyword."""
        if self._cached_accepts_messages is not None:
            return self._cached_accepts_messages
        try:
            sig = inspect.signature(self._delegate.sync_turn)
        except (TypeError, ValueError):
            self._cached_accepts_messages = True
            return self._cached_accepts_messages
        params = list(sig.parameters.values())
        self._cached_accepts_messages = (
            any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params)
            or "messages" in sig.parameters
        )
        return self._cached_accepts_messages

    def close(self) -> None:
        """Close underlying connections.  Override in subclasses that manage
        their own connection pools (e.g. RetainDB SQLite thread-locals)."""
        close_fn = getattr(self._delegate, "close", None)
        if callable(close_fn):
            close_fn()


class _GenericAdapter(_SubProviderAdapter):
    """Adapter for ANY MemoryProvider loaded via Hermes's plugin discovery.

    Used as a fallback when a backend name doesn't match any hardcoded adapter.
    The provider is loaded via ``load_memory_provider(name)`` from
    ``plugins.memory``.  Tool names are NOT prefixed — the provider is
    responsible for its own naming convention.
    """

    CONFIG_KEY = ""  # Set dynamically
    PREFIX = ""  # No prefix — provider handles its own names

    def __init__(self, provider: Any, name: str, **kwargs: Any):
        self._delegate = provider
        self._name = name
        # Cache introspection results
        self._cached_write_mode: str | None = None
        self._cached_accepts_messages: bool | None = None

    @property
    def name(self) -> str:
        return self._name

    def get_tool_schemas(self) -> list[dict]:
        # Don't prefix — the provider handles its own tool names
        return self._delegate.get_tool_schemas()

    def handle_tool_call(self, tool_name: str, args: dict, **kwargs: Any) -> str:
        # Don't strip prefix — pass through as-is
        return self._delegate.handle_tool_call(tool_name, args, **kwargs)


# ── Concrete adapters ──────────────────────────────────────────────────────


class _MnemosyneAdapter(_SubProviderAdapter):
    CONFIG_KEY = "mnemosyne"
    MODULE = "mnemosyne"
    CLASS = "MemoryProvider"
    PREFIX = "mnemosyne"  # stdlib-backed, no extra pip deps

    # Mnemosyne's install script creates the plugin directory as
    # "hermes-mnemosyne" (not "mnemosyne"), so we search both names.
    _DISCOVERY_NAMES = ("mnemosyne", "hermes-mnemosyne")

    def __init__(self, **kwargs: Any):
        provider = self._load_via_discovery()
        if provider is not None:
            self._delegate = provider
            self._cached_write_mode = None
            self._cached_accepts_messages = None
        else:
            # Fallback to standard import when running outside Hermes
            super().__init__(**kwargs)

    @classmethod
    def _load_via_discovery(cls) -> Any:
        """Try Hermes plugin discovery for each known directory name."""
        try:
            from plugins.memory import load_memory_provider  # noqa: PLC0415
        except ImportError:
            return None
        for name in cls._DISCOVERY_NAMES:
            provider = load_memory_provider(name)
            if provider is not None:
                return provider
        return None

    @property
    def name(self) -> str:
        # Override needed because mnemosyne's real provider may report a
        # different name than the canonical "mnemosyne" used by config.
        return "mnemosyne"

    def get_tool_schemas(self) -> list[dict]:
        # Mnemosyne's tools are ALREADY prefixed ("mnemosyne_recall"),
        # don't double-prefix like the base class does.
        return self._delegate.get_tool_schemas()


class _Mem0Adapter(_SubProviderAdapter):
    CONFIG_KEY = "mem0"
    MODULE = "plugins.memory.mem0"
    CLASS = "Mem0MemoryProvider"
    PREFIX = "mem0"


class _HolographicAdapter(_SubProviderAdapter):
    CONFIG_KEY = "holographic"
    MODULE = "plugins.memory.holographic"
    CLASS = "HolographicMemoryProvider"
    PREFIX = "holographic"

    def handle_tool_call(self, tool_name: str, args: dict, **kwargs: Any) -> str:
        # Holographic doesn't self-prefix (tools are "fact_store", not
        # "holographic_fact_store"). Strip our prefix before dispatching.
        pfx = f"{self.PREFIX}_"
        if tool_name.startswith(pfx):
            tool_name = tool_name[len(pfx) :]
        return self._delegate.handle_tool_call(tool_name, args, **kwargs)


class _HonchoAdapter(_SubProviderAdapter):
    CONFIG_KEY = "honcho"
    MODULE = "plugins.memory.honcho"
    CLASS = "HonchoMemoryProvider"
    PREFIX = "honcho"


class _OpenVikingAdapter(_SubProviderAdapter):
    CONFIG_KEY = "openviking"
    MODULE = "plugins.memory.openviking"
    CLASS = "OpenVikingMemoryProvider"
    PREFIX = "viking"  # tool prefix differs from config key


class _HindsightAdapter(_SubProviderAdapter):
    CONFIG_KEY = "hindsight"
    MODULE = "plugins.memory.hindsight"
    CLASS = "HindsightMemoryProvider"
    PREFIX = "hindsight"


class _RetainDBAdapter(_SubProviderAdapter):
    CONFIG_KEY = "retaindb"
    MODULE = "plugins.memory.retaindb"
    CLASS = "RetainDBMemoryProvider"
    PREFIX = "retaindb"

    def close(self) -> None:
        """Shutdown writer threads and close SQLite thread-local connections."""
        close_fn = getattr(self._delegate, "close", None)
        if callable(close_fn):
            close_fn()
        else:
            self._delegate.shutdown()


class _ByteRoverAdapter(_SubProviderAdapter):
    CONFIG_KEY = "byterover"
    MODULE = "plugins.memory.byterover"
    CLASS = "ByteRoverMemoryProvider"
    PREFIX = "brv"  # tool prefix differs from config key


class _SupermemoryAdapter(_SubProviderAdapter):
    CONFIG_KEY = "supermemory"
    MODULE = "plugins.memory.supermemory"
    CLASS = "SupermemoryMemoryProvider"
    PREFIX = "supermemory"
