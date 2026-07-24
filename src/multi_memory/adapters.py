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

# Plugin directory names Mnemosyne may be installed under.
# ``mnemosyne`` is the canonical name; ``hermes-mnemosyne`` is the
# pip-package-matching name some install scripts create.
MNEMOSYNE_PLUGIN_DIRS: tuple[str, ...] = ("mnemosyne", "hermes-mnemosyne")


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
        logger.warning(
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
        name = str(s.get("name", "") or "")
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
        self._init_caches()

    def _init_caches(self) -> _SubProviderAdapter:
        """Initialize introspection cache fields, returning ``self`` for chaining.

        Subclasses that bypass ``__init__`` (e.g. ``_GenericAdapter``,
        ``_MnemosyneAdapter``) call this instead of duplicating cache
        field assignments — all cache fields are declared in one place.
        """
        self._cached_write_mode: str | None = None
        self._cached_accepts_messages: bool | None = None
        return self

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
        """Close underlying connections, falling back to ``shutdown()``.

        Override in subclasses that manage their own connection pools
        (e.g. RetainDB SQLite thread-locals).
        """
        close_fn = getattr(self._delegate, "close", None)
        if callable(close_fn):
            close_fn()
        else:
            self._delegate.shutdown()

    def get_config_schema(self) -> list[dict]:
        """Forward the delegate's config schema for ``hermes memory setup``."""
        from typing import cast  # noqa: PLC0415

        fn = getattr(self._delegate, "get_config_schema", None)
        return list(cast(list[dict], fn())) if callable(fn) else []

    def save_config(self, values: dict[str, Any], hermes_home: str) -> None:
        """Forward config writes to the delegate."""
        fn = getattr(self._delegate, "save_config", None)
        if callable(fn):
            fn(values, hermes_home)

    def backup_paths(self) -> list[str]:
        """Forward external paths declared by the delegate for `hermes backup`."""
        from typing import cast  # noqa: PLC0415

        fn = getattr(self._delegate, "backup_paths", None)
        return list(cast(list[str], fn())) if callable(fn) else []


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
        # Bypass _SubProviderAdapter.__init__ which calls _try_import.
        # The provider is already loaded — just store it and init caches.
        self._delegate = provider
        self._name = name
        self._init_caches()

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
    PREFIX = "mnemosyne"

    def __init__(self, **kwargs: Any):
        # Import the Mnemosyne provider directly — load_memory_provider
        # resolves the plugin from ~/.hermes/plugins/ by name.
        # We do NOT call discover_memory_providers() because it enumerates
        # ALL backends, including Honcho which can hang when missing config.
        provider = None
        try:
            from plugins.memory import load_memory_provider  # noqa: PLC0415
        except ImportError:
            pass
        else:
            # Try both possible plugin directory names
            for dirname in MNEMOSYNE_PLUGIN_DIRS:
                try:
                    provider = load_memory_provider(dirname)
                except Exception as exc:
                    logger.debug(
                        "[multi-memory] load_memory_provider('%s') failed: %s",
                        dirname,
                        exc,
                    )
                    continue
                if provider is not None:
                    break
        if provider is not None:
            self._delegate = provider
            self._init_caches()
        else:
            raise RuntimeError(
                "[multi-memory] Mnemosyne plugin not found. "
                "Install it with:\n"
                "  pip install mnemosyne-memory\n"
                "  mnemosyne-hermes install\n"
                "Then restart Hermes."
            )

    @property
    def name(self) -> str:
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
