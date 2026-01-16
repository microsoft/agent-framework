# Copyright (c) Microsoft. All rights reserved.

"""Durable Shared State for Workflow Execution

This module provides a durable SharedState implementation that allows executors
in a workflow to share state across the execution lifecycle. Unlike MAF's in-memory
SharedState which uses async locks, this implementation is backed by Azure Durable
Entities for durability and replay-safety.

Key features:
- DurableSharedState: Orchestration-side wrapper for shared state operations
- SharedStateEntity: Entity function that stores the shared state
- Compatible API with agent_framework SharedState

Usage:
    In run_workflow_orchestrator:
        shared_state = DurableSharedState(context, session_id)
        value = yield shared_state.get("my_key")
        yield shared_state.set("my_key", "my_value")
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from dataclasses import dataclass, field
from typing import Any

from azure.durable_functions import DurableOrchestrationContext, EntityId

logger = logging.getLogger(__name__)

# Entity name for SharedState
SHARED_STATE_ENTITY_NAME = "SharedStateEntity"


@dataclass
class SharedStateData:
    """The underlying data structure for shared state.

    This is stored as the state of the SharedStateEntity.
    """

    state: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for entity storage."""
        return {"state": self.state}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> SharedStateData:
        """Deserialize from entity state."""
        if data is None:
            return cls()
        return cls(state=data.get("state", {}))


class DurableSharedState:
    """Orchestration-side wrapper for shared state operations.

    This class provides a generator-based API compatible with Durable Functions
    orchestrations. Each operation (get, set, has, delete) returns a generator
    that yields entity calls.

    The shared state is scoped to a workflow session using the session_id as
    the entity instance id.

    Example:
        shared_state = DurableSharedState(context, "session-123")

        # Get a value
        value = yield from shared_state.get("my_key")

        # Set a value
        yield from shared_state.set("my_key", {"data": "value"})

        # Check if key exists
        exists = yield from shared_state.has("my_key")

        # Delete a key
        yield from shared_state.delete("my_key")

        # Get all state
        all_state = yield from shared_state.get_all()
    """

    def __init__(self, context: DurableOrchestrationContext, session_id: str) -> None:
        """Initialize the shared state wrapper.

        Args:
            context: The Durable Functions orchestration context
            session_id: The session identifier used as the entity instance id
        """
        self._context = context
        self._session_id = session_id
        self._entity_id = EntityId(SHARED_STATE_ENTITY_NAME, session_id)

    @property
    def entity_id(self) -> EntityId:
        """Get the entity ID for this shared state instance."""
        return self._entity_id

    def get(self, key: str, default: Any = None) -> Generator[Any, Any, Any]:
        """Get a value from the shared state.

        Args:
            key: The key to retrieve
            default: Default value if key doesn't exist

        Returns:
            Generator that yields the value or default
        """
        result = yield self._context.call_entity(self._entity_id, "get", {"key": key, "default": default})
        return result

    def set(self, key: str, value: Any) -> Generator[Any, Any, None]:
        """Set a value in the shared state.

        Args:
            key: The key to set
            value: The value to store (must be JSON serializable)
        """
        yield self._context.call_entity(self._entity_id, "set", {"key": key, "value": value})

    def has(self, key: str) -> Generator[Any, Any, bool]:
        """Check if a key exists in the shared state.

        Args:
            key: The key to check

        Returns:
            Generator that yields True if key exists, False otherwise
        """
        result = yield self._context.call_entity(self._entity_id, "has", {"key": key})
        return result

    def delete(self, key: str) -> Generator[Any, Any, bool]:
        """Delete a key from the shared state.

        Args:
            key: The key to delete

        Returns:
            Generator that yields True if key was deleted, False if it didn't exist
        """
        result = yield self._context.call_entity(self._entity_id, "delete", {"key": key})
        return result

    def get_all(self) -> Generator[Any, Any, dict[str, Any]]:
        """Get all shared state as a dictionary.

        Returns:
            Generator that yields the complete state dictionary
        """
        result = yield self._context.call_entity(self._entity_id, "get_all", None)
        return result if result else {}

    def update(self, updates: dict[str, Any]) -> Generator[Any, Any, None]:
        """Update multiple keys at once.

        Args:
            updates: Dictionary of key-value pairs to update
        """
        yield self._context.call_entity(self._entity_id, "update", {"updates": updates})

    def clear(self) -> Generator[Any, Any, None]:
        """Clear all shared state."""
        yield self._context.call_entity(self._entity_id, "clear", None)


def create_shared_state_entity_function():
    """Create the entity function for SharedState.

    This function handles all shared state operations:
    - get: Retrieve a value by key
    - set: Store a value by key
    - has: Check if a key exists
    - delete: Remove a key
    - get_all: Get the complete state dictionary
    - update: Update multiple keys at once
    - clear: Clear all state

    Returns:
        The entity function to be registered with the Durable Functions app
    """

    def shared_state_entity(context):
        """Entity function for SharedState storage."""
        # Get or initialize state
        current_state = context.get_state(lambda: {"state": {}})
        state_data = SharedStateData.from_dict(current_state)

        operation = context.operation_name
        operation_input = context.get_input()

        logger.debug("[SharedState] Operation: %s, Input: %s", operation, operation_input)

        if operation == "get":
            key = operation_input.get("key")
            default = operation_input.get("default")
            result = state_data.state.get(key, default)
            context.set_result(result)

        elif operation == "set":
            key = operation_input.get("key")
            value = operation_input.get("value")
            state_data.state[key] = value
            context.set_state(state_data.to_dict())

        elif operation == "has":
            key = operation_input.get("key")
            result = key in state_data.state
            context.set_result(result)

        elif operation == "delete":
            key = operation_input.get("key")
            if key in state_data.state:
                del state_data.state[key]
                context.set_state(state_data.to_dict())
                context.set_result(True)
            else:
                context.set_result(False)

        elif operation == "get_all":
            context.set_result(state_data.state.copy())

        elif operation == "update":
            updates = operation_input.get("updates", {})
            state_data.state.update(updates)
            context.set_state(state_data.to_dict())

        elif operation == "clear":
            state_data.state.clear()
            context.set_state(state_data.to_dict())

        else:
            logger.warning("[SharedState] Unknown operation: %s", operation)

    return shared_state_entity
