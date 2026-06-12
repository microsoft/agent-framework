# Copyright (c) Microsoft. All rights reserved.

"""AG-UI Thread Snapshot storage primitives."""

from __future__ import annotations

import copy
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, TypeAlias, runtime_checkable

if TYPE_CHECKING:
    from ._types import AGUIRequest

SnapshotScope: TypeAlias = str
"""Application-defined scope for authorizing access to AG-UI Thread Snapshots."""

AGUIThreadID: TypeAlias = str
"""AG-UI Thread identifier within a Snapshot Scope."""

SnapshotScopeResolver: TypeAlias = Callable[["AGUIRequest"], str | Awaitable[str]]
"""Callable that resolves the Snapshot Scope for an AG-UI endpoint request."""

_SnapshotKey: TypeAlias = tuple[SnapshotScope, AGUIThreadID]

DEFAULT_MAX_THREAD_SNAPSHOTS = 1_000
_SNAPSHOT_SCOPE_INPUT_KEY = "__ag_ui_snapshot_scope"
_DEFAULT_STATE_INPUT_KEY = "__ag_ui_default_state"


@dataclass(slots=True)
class AGUIThreadSnapshot:
    """Replayable AG-UI Thread state.

    AG-UI Thread Snapshots intentionally contain only data that can be replayed
    to a UI: message snapshots, optional Shared State, and optional interruption
    state. They do not include raw events, request metadata, auth claims,
    diagnostics, traces, or provider responses.

    Attributes:
        messages: Replayable AG-UI message snapshots.
        state: Optional AG-UI Shared State snapshot.
        interrupt: Optional interruption state from ``RUN_FINISHED.interrupt``.
    """

    messages: list[dict[str, Any]] = field(default_factory=list)
    state: dict[str, Any] | None = None
    interrupt: list[dict[str, Any]] | None = None


@runtime_checkable
class AGUIThreadSnapshotStore(Protocol):
    """Async store for latest AG-UI Thread Snapshots keyed by scope and thread id."""

    async def save(
        self,
        *,
        scope: SnapshotScope,
        thread_id: AGUIThreadID,
        snapshot: AGUIThreadSnapshot,
    ) -> None:
        """Save the latest snapshot for an AG-UI Thread within a Snapshot Scope.

        Args:
            scope: Application-defined Snapshot Scope. This is part of the
                storage key and must represent the app's authorization boundary.
            thread_id: AG-UI Thread id within the scope.
            snapshot: Snapshot to save.
        """
        ...

    async def get(
        self,
        *,
        scope: SnapshotScope,
        thread_id: AGUIThreadID,
    ) -> AGUIThreadSnapshot | None:
        """Get the latest snapshot for an AG-UI Thread within a Snapshot Scope.

        Args:
            scope: Application-defined Snapshot Scope.
            thread_id: AG-UI Thread id within the scope.

        Returns:
            The latest snapshot, or ``None`` when no snapshot exists for the key.
        """
        ...

    async def delete(
        self,
        *,
        scope: SnapshotScope,
        thread_id: AGUIThreadID,
    ) -> bool:
        """Delete the latest snapshot for an AG-UI Thread within a Snapshot Scope.

        Args:
            scope: Application-defined Snapshot Scope.
            thread_id: AG-UI Thread id within the scope.

        Returns:
            ``True`` when a snapshot was deleted, otherwise ``False``.
        """
        ...

    async def clear(self, *, scope: SnapshotScope | None = None) -> None:
        """Clear saved snapshots.

        Args:
            scope: Optional Snapshot Scope to clear. When omitted, all in-memory
                snapshots are cleared.
        """
        ...


class InMemoryAGUIThreadSnapshotStore:
    """Bounded memory-only latest snapshot store for local development, demos, and tests.

    This store keeps at most one snapshot per ``(scope, thread_id)`` key. It is
    process-local and not durable production storage.
    """

    def __init__(self, *, max_snapshots: int = DEFAULT_MAX_THREAD_SNAPSHOTS) -> None:
        """Initialize the in-memory snapshot store.

        Keyword Args:
            max_snapshots: Maximum number of scoped thread snapshots to retain.

        Raises:
            ValueError: If ``max_snapshots`` is less than 1.
        """
        if max_snapshots < 1:
            raise ValueError("max_snapshots must be greater than 0.")
        self._max_snapshots = max_snapshots
        self._snapshots: dict[_SnapshotKey, AGUIThreadSnapshot] = {}

    async def save(
        self,
        *,
        scope: SnapshotScope,
        thread_id: AGUIThreadID,
        snapshot: AGUIThreadSnapshot,
    ) -> None:
        """Save the latest snapshot for an AG-UI Thread within a Snapshot Scope."""
        key = self._key(scope=scope, thread_id=thread_id)
        if key in self._snapshots:
            del self._snapshots[key]
        self._snapshots[key] = copy.deepcopy(snapshot)
        self._evict_oldest()

    async def get(
        self,
        *,
        scope: SnapshotScope,
        thread_id: AGUIThreadID,
    ) -> AGUIThreadSnapshot | None:
        """Get the latest snapshot for an AG-UI Thread within a Snapshot Scope."""
        snapshot = self._snapshots.get(self._key(scope=scope, thread_id=thread_id))
        return copy.deepcopy(snapshot) if snapshot is not None else None

    async def delete(
        self,
        *,
        scope: SnapshotScope,
        thread_id: AGUIThreadID,
    ) -> bool:
        """Delete the latest snapshot for an AG-UI Thread within a Snapshot Scope."""
        key = self._key(scope=scope, thread_id=thread_id)
        if key not in self._snapshots:
            return False
        del self._snapshots[key]
        return True

    async def clear(self, *, scope: SnapshotScope | None = None) -> None:
        """Clear saved snapshots, optionally limited to one Snapshot Scope."""
        if scope is None:
            self._snapshots.clear()
            return

        normalized_scope = self._normalize_key_part(scope, "scope")
        for key in list(self._snapshots):
            if key[0] == normalized_scope:
                del self._snapshots[key]

    @classmethod
    def _key(cls, *, scope: SnapshotScope, thread_id: AGUIThreadID) -> _SnapshotKey:
        return (
            cls._normalize_key_part(scope, "scope"),
            cls._normalize_key_part(thread_id, "thread_id"),
        )

    @staticmethod
    def _normalize_key_part(value: str, name: str) -> str:
        if not isinstance(value, str):
            raise TypeError(f"{name} must be a string.")
        if not value:
            raise ValueError(f"{name} must be a non-empty string.")
        return value

    def _evict_oldest(self) -> None:
        while len(self._snapshots) > self._max_snapshots:
            del self._snapshots[next(iter(self._snapshots))]
