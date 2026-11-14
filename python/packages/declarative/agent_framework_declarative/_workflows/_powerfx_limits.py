# Copyright (c) Microsoft. All rights reserved.

"""Structural budgets for state copying and PowerFx symbol conversion.

Each traversal has its own budget and rejects cycles or excess with ValueError,
rather than truncating values. These limits do not bound expression execution
or application-defined Python copy/conversion hooks.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, cast

_MAX_POWERFX_STATE_DEPTH = 64
_MAX_POWERFX_STATE_NODES = 10_000
_MAX_POWERFX_STATE_TEXT_SIZE = 1_048_576


class _PowerFxStateLimitError(ValueError):
    """State cannot be copied or marshalled within the PowerFx budget."""


@dataclass
class _PowerFxStateBudget:
    """Count values, containers, and mapping keys, including repeated aliases.

    Depth starts at zero. Text size counts string characters and binary bytes,
    not encoded size or total memory.
    """

    nodes: int = 0
    text_size: int = 0

    def consume(self, item: Any, depth: int) -> None:
        self.nodes += 1
        if self.nodes > _MAX_POWERFX_STATE_NODES:
            raise _PowerFxStateLimitError("PowerFx state exceeds the node budget")
        if depth > _MAX_POWERFX_STATE_DEPTH:
            raise _PowerFxStateLimitError("PowerFx state exceeds the depth budget")
        if isinstance(item, (str, bytes, bytearray)):
            self.text_size += len(item)
            if self.text_size > _MAX_POWERFX_STATE_TEXT_SIZE:
                raise _PowerFxStateLimitError("PowerFx state exceeds the text size budget")


def _validate_powerfx_state(value: Any) -> None:  # pyright: ignore[reportUnusedFunction]
    """Reject cyclic or over-budget data before copying or conversion."""
    budget = _PowerFxStateBudget()
    active: set[int] = set()

    def visit(item: Any, depth: int) -> None:
        budget.consume(item, depth)
        if item is None or isinstance(item, (str, bytes, bytearray, bool, int, float)):
            return

        identity = id(item)
        if identity in active:
            raise _PowerFxStateLimitError("PowerFx state contains a cycle")
        active.add(identity)
        try:
            if isinstance(item, Enum):
                visit(item.value, depth + 1)
            elif isinstance(item, Mapping):
                for key, member in cast(Mapping[Any, Any], item).items():
                    visit(key, depth + 1)
                    visit(member, depth + 1)
            elif isinstance(item, (list, tuple, set, frozenset)):
                for member in cast(list[Any] | tuple[Any, ...] | set[Any] | frozenset[Any], item):
                    visit(member, depth + 1)
            elif hasattr(item, "__dict__"):
                visit(vars(item), depth + 1)
        finally:
            active.remove(identity)

    visit(value, 0)
