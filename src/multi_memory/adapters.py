"""Adapter layer that wraps Hermes MemoryProvider subclasses into a common interface.

Each known backend (Mnemosyne, Mem0, Holographic, Honcho) has a thin
``_SubProviderAdapter`` subclass that delegates lifecycle calls to
the real provider while prefixing tool names to avoid collisions.

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
    if find_spec(module) is None:
        return None
    try:
        mod = importlib.import_module(module)
        return getattr(mod, cls, None)
    except Exception:
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

    def on_turn_start(self) -> None:
        self._delegate.on_turn_start()

    def on_session_end(self, messages: list[dict]) -> None:
        self._delegate.on_session_end(messages)

    def on_session_switch(self) -> None:
        self._delegate.on_session_switch()

    def on_memory_write(self, action: str, target: str, content: str) -> None:
        self._delegate.on_memory_write(action, target, content)

    def on_delegation(self) -> None:
        self._delegate.on_delegation()


class _MnemosyneAdapter(_SubProviderAdapter):
    CONFIG_KEY = "mnemosyne"
    MODULE     = "mnemosyne"
    CLASS      = "MemoryProvider"
    PREFIX     = "mnemosyne"   # stdlib-backed, no extra pip deps

    @property
    def name(self) -> str:
        return "mnemosyne"


class _Mem0Adapter(_SubProviderAdapter):
    CONFIG_KEY = "mem0"
    MODULE     = "plugins.memory.mem0"
    CLASS      = "Mem0MemoryProvider"
    PREFIX     = "mem0"


class _HolographicAdapter(_SubProviderAdapter):
    CONFIG_KEY = "holographic"
    MODULE     = "plugins.memory.holographic"
    CLASS      = "HolographicMemoryProvider"
    PREFIX     = "holographic"


class _HonchoAdapter(_SubProviderAdapter):
    CONFIG_KEY = "honcho"
    MODULE     = "plugins.memory.honcho"
    CLASS      = "HonchoMemoryProvider"
    PREFIX     = "honcho"
