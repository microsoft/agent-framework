# Copyright (c) Microsoft. All rights reserved.

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any


class SharedState:
    """A class to manage shared state in a workflow.

    SharedState provides thread-safe access to workflow state data that needs to be
    shared across executors during workflow execution.

    Reserved Keys:
        The following keys are reserved for internal framework use and should not be
        modified by user code:

        - `_executor_state`: Stores executor state for checkpointing (managed by Runner)

    Warning:
        Do not use keys starting with underscore (_) as they may be reserved for
        internal framework operations.
    """

    def __init__(self) -> None:
        """Initialize the shared state."""
        self._state: dict[str, Any] = {}
        self._shared_state_lock = asyncio.Lock()

    async def set(self, key: str, value: Any) -> None:
        """Set a value in the shared state."""
        async with self._shared_state_lock:
            await self.set_within_hold(key, value)

    async def get(self, key: str) -> Any:
        """Get a value from the shared state."""
        async with self._shared_state_lock:
            return await self.get_within_hold(key)

    async def has(self, key: str) -> bool:
        """Check if a key exists in the shared state."""
        async with self._shared_state_lock:
            return await self.has_within_hold(key)

    async def delete(self, key: str) -> None:
        """Delete a key from the shared state."""
        async with self._shared_state_lock:
            await self.delete_within_hold(key)

    async def clear(self) -> None:
        """Clear the entire shared state."""
        async with self._shared_state_lock:
            self._state.clear()

    async def export_state(self) -> dict[str, Any]:
        """Get a serialized copy of the entire shared state."""
        async with self._shared_state_lock:
            return dict(self._state)

    async def import_state(self, state: dict[str, Any]) -> None:
        """Populate the shared state from a serialized state dictionary.

        This replaces the entire current state with the provided state.
        """
        async with self._shared_state_lock:
            self._state.update(state)

    @asynccontextmanager
    async def hold(self) -> AsyncIterator["SharedState"]:
        """Context manager to hold the shared state lock for multiple operations.

        Usage:
            async with shared_state.hold():
                await shared_state.set_within_hold("key", value)
                value = await shared_state.get_within_hold("key")
        """
        async with self._shared_state_lock:
            yield self

    # Unsafe methods that don't acquire locks (for use within hold() context)
    async def set_within_hold(self, key: str, value: Any) -> None:
        """Set a value without acquiring the lock (unsafe - use within hold() context)."""
        self._state[key] = value

    async def get_within_hold(self, key: str) -> Any:
        """Get a value without acquiring the lock (unsafe - use within hold() context)."""
        if key not in self._state:
            raise KeyError(f"Key '{key}' not found in shared state.")
        return self._state[key]

    async def has_within_hold(self, key: str) -> bool:
        """Check if a key exists without acquiring the lock (unsafe - use within hold() context)."""
        return key in self._state

    async def delete_within_hold(self, key: str) -> None:
        """Delete a key without acquiring the lock (unsafe - use within hold() context)."""
        if key in self._state:
            del self._state[key]
        else:
            raise KeyError(f"Key '{key}' not found in shared state.")
