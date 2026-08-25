# Copyright (c) Microsoft. All rights reserved.

"""A2UI (agent-generated UI) support for the AG-UI Agent Framework adapter.

Toolkit-dependent exports (``A2UIAgent`` / ``enable_a2ui`` / ``plan_a2ui_injection`` /
``is_a2ui_runner``) are loaded lazily via PEP 562 so this package — and the toolkit-free
context-plumbing helpers in :mod:`._state` it re-exports — can be imported by the hosting
loop even when ``ag-ui-a2ui-toolkit`` is not installed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

# Toolkit-free helpers — safe to import eagerly (no ag_ui_a2ui_toolkit dependency).
from ._state import (
    A2UI_SCHEMA_CONTEXT_DESCRIPTION,
    build_ag_ui_context_slice,
    read_inject_a2ui_flag,
)

if TYPE_CHECKING:
    from ._agent import A2UIAgent
    from ._factory import enable_a2ui, is_a2ui_runner, plan_a2ui_injection

__all__ = [
    "A2UI_SCHEMA_CONTEXT_DESCRIPTION",
    "A2UIAgent",
    "build_ag_ui_context_slice",
    "enable_a2ui",
    "is_a2ui_runner",
    "plan_a2ui_injection",
    "read_inject_a2ui_flag",
]

# Lazy (toolkit-dependent) exports: module -> symbols defined there.
_LAZY: dict[str, tuple[str, ...]] = {
    "_agent": ("A2UIAgent",),
    "_factory": ("enable_a2ui", "is_a2ui_runner", "plan_a2ui_injection"),
}


def __getattr__(name: str) -> Any:
    for module, symbols in _LAZY.items():
        if name in symbols:
            import importlib

            mod = importlib.import_module(f".{module}", __name__)
            return getattr(mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
