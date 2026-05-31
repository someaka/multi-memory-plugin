"""Adapter layer that wraps Hermes MemoryProvider subclasses into a common interface.

Each known backend (Mnemosyne, Mem0, Holographic, Honcho, Chroma, Pinecone,
Weaviate, Qdrant, Milvus) has a thin ``_SubProviderAdapter`` subclass that
delegates lifecycle calls to the real provider while prefixing tool names
to avoid collisions.

Usage
-----
Adapters are not instantiated directly — the ``MultiMemoryProvider``
in ``__init__.py`` discovers and instantiates them from config.
"""

from __future__ import annotations

from importlib.util import find_spec
import importlib
import logging
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
            module, cls, exc,
        )
        return None


class _SubProviderAdapter:
    """Base class for all sub-provider adapters — thin delegation wrapper."""

    CONFIG_KEY: str = ""
    MODULE:     str = ""
    CLASS:      str = ""
    PREFIX:     str = ""   # tool name prefix = config-key (full name avoids collision)

    def __init__(self, **kwargs: Any):
        real_cls = _try_import(self.MODULE, self.CLASS)
        if real_cls is None:
            raise RuntimeError(
                f"[multi-memory] backend '{self.CONFIG_KEY}' not installed "
                f"(pip install {self.CONFIG_KEY!r})"
            )
        self._delegate = real_cls()

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
        return [{**s, "name": f"{self.PREFIX}_{s['name']}"} for s in raw]

    def handle_tool_call(self, tool_name: str, args: dict, **kwargs: Any) -> str:
        inner = tool_name[len(self.PREFIX) + 1:]
        return self._delegate.handle_tool_call(inner, args, **kwargs)

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        return self._delegate.prefetch(query, session_id=session_id)

    def queue_prefetch(self, query: str, *, session_id: str = "") -> None:
        self._delegate.queue_prefetch(query, session_id=session_id)

    def sync_turn(self, user_content: str, assistant_content: str, *, session_id: str = "") -> None:
        self._delegate.sync_turn(user_content, assistant_content, session_id=session_id)

    def system_prompt_block(self) -> str:
        return self._delegate.system_prompt_block()

    def on_turn_start(self, turn_number: int = 0, message: str = "", **kwargs: Any) -> None:
        self._delegate.on_turn_start(turn_number, message, **kwargs)

    def on_session_end(self, messages: list[dict]) -> None:
        self._delegate.on_session_end(messages)

    def on_session_switch(self, new_session_id: str = "", *, parent_session_id: str = "", reset: bool = False, **kwargs: Any) -> None:
        self._delegate.on_session_switch(new_session_id, parent_session_id=parent_session_id, reset=reset, **kwargs)

    def on_memory_write(self, action: str, target: str, content: str, metadata: dict[str, Any] | None = None) -> None:
        self._delegate.on_memory_write(action, target, content, metadata)

    def on_delegation(self, task: str = "", result: str = "", *, child_session_id: str = "", **kwargs: Any) -> None:
        self._delegate.on_delegation(task, result, child_session_id=child_session_id, **kwargs)

    def on_pre_compress(self, messages: list[dict[str, Any]]) -> str:
        return self._delegate.on_pre_compress(messages)

    def close(self) -> None:
        """Close underlying connections.  Override in subclasses that manage
        their own connection pools (e.g. RetainDB SQLite thread-locals)."""
        close_fn = getattr(self._delegate, 'close', None)
        if callable(close_fn):
            close_fn()


class _MnemosyneAdapter(_SubProviderAdapter):
    CONFIG_KEY = "mnemosyne"
    MODULE     = "mnemosyne"
    CLASS      = "MemoryProvider"
    PREFIX     = "mnemosyne"   # stdlib-backed, no extra pip deps

    def __init__(self, **kwargs: Any):
        # Mnemosyne is a user-installed plugin (~/.hermes/plugins/mnemosyne/),
        # not a pip package — use the Hermes plugin loader to find it.
        try:
            from plugins.memory import load_memory_provider
            provider = load_memory_provider("mnemosyne")
            if provider is None:
                raise ImportError(
                    "[multi-memory] backend 'mnemosyne' not found via plugin loader"
                )
            self._delegate = provider
        except ImportError:
            # Fallback to standard import when running outside Hermes
            super().__init__(**kwargs)

    @property
    def name(self) -> str:
        # Override needed because mnemosyne's real provider may report a
        # different name than the canonical "mnemosyne" used by config.
        return "mnemosyne"

    def handle_tool_call(self, tool_name: str, args: dict, **kwargs: Any) -> str:
        # Mnemosyne uses FULL prefixed tool names internally
        # (e.g. "mnemosyne_recall", not "recall") — don't strip.
        return self._delegate.handle_tool_call(tool_name, args, **kwargs)

    def get_tool_schemas(self) -> list[dict]:
        # Mnemosyne's tools are ALREADY prefixed ("mnemosyne_recall"),
        # don't double-prefix like the base class does.
        return self._delegate.get_tool_schemas()


class _Mem0Adapter(_SubProviderAdapter):
    CONFIG_KEY = "mem0"
    MODULE     = "plugins.memory.mem0"
    CLASS      = "Mem0MemoryProvider"
    PREFIX     = "mem0"

    def get_tool_schemas(self) -> list[dict]:
        # Mem0's tools are already prefixed ("mem0_profile") — strip the
        # existing prefix so we end up with exactly one "mem0_" prefix.
        raw = self._delegate.get_tool_schemas()
        pfx = f"{self.PREFIX}_"
        stripped = [
            {**s, "name": s["name"][len(pfx):] if s["name"].startswith(pfx) else s["name"]}
            for s in raw
        ]
        return [{**s, "name": f"{self.PREFIX}_{s['name']}"} for s in stripped]

    def handle_tool_call(self, tool_name: str, args: dict, **kwargs: Any) -> str:
        # Mem0 expects full prefixed names ("mem0_search") — don't strip.
        return self._delegate.handle_tool_call(tool_name, args, **kwargs)


class _HolographicAdapter(_SubProviderAdapter):
    CONFIG_KEY = "holographic"
    MODULE     = "plugins.memory.holographic"
    CLASS      = "HolographicMemoryProvider"
    PREFIX     = "holographic"

    def get_tool_schemas(self) -> list[dict]:
        # Holographic tools may be self-prefixed ("holographic_store") or
        # unprefixed ("fact_store") depending on version — strip+re-add to
        # guarantee exactly one prefix.
        raw = self._delegate.get_tool_schemas()
        pfx = f"{self.PREFIX}_"
        stripped = [
            {**s, "name": s["name"][len(pfx):] if s["name"].startswith(pfx) else s["name"]}
            for s in raw
        ]
        return [{**s, "name": f"{self.PREFIX}_{s['name']}"} for s in stripped]

    def handle_tool_call(self, tool_name: str, args: dict, **kwargs: Any) -> str:
        # Holographic expects full prefixed names — don't strip.
        return self._delegate.handle_tool_call(tool_name, args, **kwargs)


class _HonchoAdapter(_SubProviderAdapter):
    CONFIG_KEY = "honcho"
    MODULE     = "plugins.memory.honcho"
    CLASS      = "HonchoMemoryProvider"
    PREFIX     = "honcho"

    def get_tool_schemas(self) -> list[dict]:
        # Honcho's tools are already prefixed ("honcho_profile") — strip the
        # existing prefix so the base class adds exactly one "honcho_" prefix.
        raw = self._delegate.get_tool_schemas()
        pfx = f"{self.PREFIX}_"
        stripped = [
            {**s, "name": s["name"][len(pfx):] if s["name"].startswith(pfx) else s["name"]}
            for s in raw
        ]
        return [{**s, "name": f"{self.PREFIX}_{s['name']}"} for s in stripped]

    def handle_tool_call(self, tool_name: str, args: dict, **kwargs: Any) -> str:
        # Honcho expects full prefixed names ("honcho_search") — don't strip.
        return self._delegate.handle_tool_call(tool_name, args, **kwargs)


class _OpenVikingAdapter(_SubProviderAdapter):
    CONFIG_KEY = "openviking"
    MODULE     = "plugins.memory.openviking"
    CLASS      = "OpenVikingMemoryProvider"
    PREFIX     = "viking"  # tool prefix differs from config key

    def get_tool_schemas(self) -> list[dict]:
        # OpenViking tools are self-prefixed ("viking_search") — strip+re-add.
        raw = self._delegate.get_tool_schemas()
        pfx = f"{self.PREFIX}_"
        stripped = [
            {**s, "name": s["name"][len(pfx):] if s["name"].startswith(pfx) else s["name"]}
            for s in raw
        ]
        return [{**s, "name": f"{self.PREFIX}_{s['name']}"} for s in stripped]

    def handle_tool_call(self, tool_name: str, args: dict, **kwargs: Any) -> str:
        # OpenViking expects full prefixed names ("viking_search") — don't strip.
        return self._delegate.handle_tool_call(tool_name, args, **kwargs)


class _HindsightAdapter(_SubProviderAdapter):
    CONFIG_KEY = "hindsight"
    MODULE     = "plugins.memory.hindsight"
    CLASS      = "HindsightMemoryProvider"
    PREFIX     = "hindsight"

    def get_tool_schemas(self) -> list[dict]:
        # Hindsight tools are self-prefixed ("hindsight_retain") — strip+re-add.
        raw = self._delegate.get_tool_schemas()
        pfx = f"{self.PREFIX}_"
        stripped = [
            {**s, "name": s["name"][len(pfx):] if s["name"].startswith(pfx) else s["name"]}
            for s in raw
        ]
        return [{**s, "name": f"{self.PREFIX}_{s['name']}"} for s in stripped]

    def handle_tool_call(self, tool_name: str, args: dict, **kwargs: Any) -> str:
        # Hindsight expects full prefixed names ("hindsight_retain") — don't strip.
        return self._delegate.handle_tool_call(tool_name, args, **kwargs)


class _RetainDBAdapter(_SubProviderAdapter):
    CONFIG_KEY = "retaindb"
    MODULE     = "plugins.memory.retaindb"
    CLASS      = "RetainDBMemoryProvider"
    PREFIX     = "retaindb"

    def close(self) -> None:
        """Shutdown writer threads and close SQLite thread-local connections."""
        close_fn = getattr(self._delegate, 'close', None)
        if callable(close_fn):
            close_fn()
        else:
            # Fallback: just shutdown if close() not available
            self._delegate.shutdown()

    def get_tool_schemas(self) -> list[dict]:
        # RetainDB tools are self-prefixed ("retaindb_profile") — strip+re-add.
        raw = self._delegate.get_tool_schemas()
        pfx = f"{self.PREFIX}_"
        stripped = [
            {**s, "name": s["name"][len(pfx):] if s["name"].startswith(pfx) else s["name"]}
            for s in raw
        ]
        return [{**s, "name": f"{self.PREFIX}_{s['name']}"} for s in stripped]

    def handle_tool_call(self, tool_name: str, args: dict, **kwargs: Any) -> str:
        # RetainDB expects full prefixed names ("retaindb_profile") — don't strip.
        return self._delegate.handle_tool_call(tool_name, args, **kwargs)


class _ByteRoverAdapter(_SubProviderAdapter):
    CONFIG_KEY = "byterover"
    MODULE     = "plugins.memory.byterover"
    CLASS      = "ByteRoverMemoryProvider"
    PREFIX     = "brv"  # tool prefix differs from config key

    def get_tool_schemas(self) -> list[dict]:
        # ByteRover tools are self-prefixed ("brv_query") — strip+re-add.
        raw = self._delegate.get_tool_schemas()
        pfx = f"{self.PREFIX}_"
        stripped = [
            {**s, "name": s["name"][len(pfx):] if s["name"].startswith(pfx) else s["name"]}
            for s in raw
        ]
        return [{**s, "name": f"{self.PREFIX}_{s['name']}"} for s in stripped]

    def handle_tool_call(self, tool_name: str, args: dict, **kwargs: Any) -> str:
        # ByteRover expects full prefixed names ("brv_query") — don't strip.
        return self._delegate.handle_tool_call(tool_name, args, **kwargs)


class _SupermemoryAdapter(_SubProviderAdapter):
    CONFIG_KEY = "supermemory"
    MODULE     = "plugins.memory.supermemory"
    CLASS      = "SupermemoryMemoryProvider"
    PREFIX     = "supermemory"

    def get_tool_schemas(self) -> list[dict]:
        # Supermemory tools are self-prefixed ("supermemory_store") — strip+re-add.
        raw = self._delegate.get_tool_schemas()
        pfx = f"{self.PREFIX}_"
        stripped = [
            {**s, "name": s["name"][len(pfx):] if s["name"].startswith(pfx) else s["name"]}
            for s in raw
        ]
        return [{**s, "name": f"{self.PREFIX}_{s['name']}"} for s in stripped]

    def handle_tool_call(self, tool_name: str, args: dict, **kwargs: Any) -> str:
        # Supermemory expects full prefixed names ("supermemory_store") — don't strip.
        return self._delegate.handle_tool_call(tool_name, args, **kwargs)

