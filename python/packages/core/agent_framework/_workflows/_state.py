# Copyright (c) Microsoft. All rights reserved.

from typing import Any


class State:
    """Manages shared state across executors within a workflow.

    State provides access to workflow state data that is shared across executors
    during workflow execution. It implements superstep caching semantics where
    writes are staged in a pending buffer and only committed to the actual state
    at superstep boundaries.

    Superstep Semantics:
        - `set()` writes to a pending buffer, not directly to committed state
        - `get()` checks pending buffer first, then committed state
        - `commit()` moves all pending changes to committed state (called by Runner at superstep boundary)
        - `discard()` clears pending changes without committing

    Reserved Keys:
        Keys starting with underscore (_) are reserved for internal framework use.
        Do not use these in user code.
    """

    def __init__(self) -> None:
        """Initialize the state."""
        self._committed: dict[str, Any] = {}
        self._pending: dict[str, Any] = {}

    def set(self, key: str, value: Any) -> None:
        """Set a value in the pending state buffer.

        The value will be visible to subsequent `get()` calls but won't be
        committed to the actual state until `commit()` is called.

        Note:
            When multiple executors run concurrently within the same superstep,
            each executor's writes go to the same pending buffer. The last write
            for a given key wins when commit() is called. This is consistent with
            the .NET behavior and the superstep execution model where all executors
            in a superstep see the same committed state at the start.
        """
        self._pending[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from state, checking pending first then committed.

        Args:
            key: The key to retrieve.
            default: Value to return if key is not found. Defaults to None.

        Returns:
            The value if found, otherwise the default value.
        """
        if key in self._pending:
            value = self._pending[key]
            if value is _DeleteSentinel:
                return default
            return value
        return self._committed.get(key, default)

    def has(self, key: str) -> bool:
        """Check if a key exists in pending or committed state."""
        if key in self._pending:
            return self._pending[key] is not _DeleteSentinel
        return key in self._committed

    def delete(self, key: str) -> None:
        """Mark a key for deletion.

        If the key exists in committed state, a sentinel is stored in pending
        to indicate deletion at commit time. If it only exists in pending,
        it is removed from pending.
        """
        if key not in self._pending and key not in self._committed:
            raise KeyError(f"Key '{key}' not found in state.")

        if key in self._committed:
            # Mark for deletion from committed state at commit time
            self._pending[key] = _DeleteSentinel
        elif key in self._pending:
            # Only exists in pending, safe to just remove
            del self._pending[key]

    def clear(self) -> None:
        """Clear both committed and pending state."""
        self._committed.clear()
        self._pending.clear()

    def commit(self) -> None:
        """Commit pending changes to the committed state.

        Called by the Runner at superstep boundaries after successful execution.
        """
        for key, value in self._pending.items():
            if value is _DeleteSentinel:
                self._committed.pop(key, None)
            else:
                self._committed[key] = value
        self._pending.clear()

    def discard(self) -> None:
        """Discard all pending changes without committing."""
        self._pending.clear()

    def export_state(self) -> dict[str, Any]:
        """Export a serialized copy of the committed state.

        Note: Does not include pending changes.
        """
        return dict(self._committed)

    def import_state(self, state: dict[str, Any]) -> None:
        """Import state from a serialized dictionary.

        Merges into committed state. Does not affect pending changes.
        """
        self._committed.update(state)


class _DeleteSentinelType:
    """Sentinel type to mark keys for deletion in pending state."""

    pass


_DeleteSentinel = _DeleteSentinelType()
