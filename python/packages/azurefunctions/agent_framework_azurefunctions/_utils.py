# Copyright (c) Microsoft. All rights reserved.

"""
Utility functions for workflow execution.

This module provides helper functions for serialization, deserialization, and
context management used by the workflow orchestrator and executors.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, fields, is_dataclass
from typing import Any

from agent_framework import AgentExecutorRequest, AgentExecutorResponse, AgentRunResponse, ChatMessage
from agent_framework._workflows._shared_state import SharedState
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class CapturingWorkflowContext:
    """
    Context that captures outputs, sent messages, and shared state changes.

    Provides a WorkflowContext-compatible API for custom executors running
    in activities. Uses MAF's SharedState class internally, initialized with
    a snapshot from the orchestrator. After execution, changes are diffed
    against the original snapshot to determine updates and deletes.

    This class does NOT inherit from WorkflowContext to avoid requiring
    RunnerContext instances. Instead, it duck-types the interface that
    executor handlers expect.

    Use the async `create()` factory method to instantiate this class.
    """

    def __init__(self) -> None:
        """Initialize the capturing context. Use create() factory method instead."""
        self._original_snapshot: dict[str, Any] = {}
        self._shared_state = SharedState()
        self.sent_messages: list[dict[str, Any]] = []
        self.outputs: list[Any] = []

    @classmethod
    async def create(
        cls,
        shared_state_snapshot: dict[str, Any] | None = None,
    ) -> "CapturingWorkflowContext":
        """
        Create a new CapturingWorkflowContext asynchronously.

        Args:
            shared_state_snapshot: Snapshot of current shared state from orchestrator

        Returns:
            A new CapturingWorkflowContext instance
        """
        instance = cls()
        instance._original_snapshot = dict(shared_state_snapshot or {})
        await instance._shared_state.import_state(shared_state_snapshot or {})
        return instance

    @property
    def shared_state(self) -> SharedState:
        """Get the shared state object for direct access."""
        return self._shared_state

    async def send_message(self, message: Any, target_id: str | None = None) -> None:
        """Capture a message to be routed by the orchestrator."""
        self.sent_messages.append({"message": message, "target_id": target_id})

    async def yield_output(self, output: Any) -> None:
        """Capture a workflow output."""
        self.outputs.append(output)

    async def get_shared_state(self, key: str) -> Any:
        """
        Get a value from shared state.

        If the stored value has type metadata (__type__, __module__),
        attempts to reconstruct the original typed object.

        Args:
            key: The key to retrieve

        Returns:
            The value associated with the key (possibly reconstructed)

        Raises:
            KeyError: If the key doesn't exist
        """
        value = await self._shared_state.get(key)
        return deserialize_value(value)

    async def set_shared_state(self, key: str, value: Any) -> None:
        """
        Set a value in shared state.

        Args:
            key: The key to set
            value: The value to store (must be JSON serializable)
        """
        await self._shared_state.set(key, value)

    async def get_shared_state_changes(self) -> tuple[dict[str, Any], set[str]]:
        """
        Get all shared state changes made during execution.

        Compares current state against the original snapshot to find:
        - Updates: keys that were added or modified
        - Deletes: keys that were removed

        Returns:
            Tuple of (updates dict, deletes set)
        """
        current_state = await self._shared_state.export_state()
        original_keys = set(self._original_snapshot.keys())
        current_keys = set(current_state.keys())

        # Deleted = was in original, not in current
        deletes = original_keys - current_keys

        # Updates = keys in current that are new or have different values
        updates = {k: v for k, v in current_state.items() if k not in self._original_snapshot or self._original_snapshot[k] != v}

        return updates, deletes


def _serialize_value(value: Any) -> Any:
    """Recursively serialize a value for JSON compatibility."""
    # Handle None
    if value is None:
        return None

    # Handle objects with to_dict() method (like ChatMessage)
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return value.to_dict()

    # Handle dataclasses
    if is_dataclass(value) and not isinstance(value, type):
        d: dict[str, Any] = {}
        for k, v in asdict(value).items():
            d[k] = _serialize_value(v)
        d["__type__"] = type(value).__name__
        d["__module__"] = type(value).__module__
        return d

    # Handle Pydantic models
    if isinstance(value, BaseModel):
        d = value.model_dump()
        d["__type__"] = type(value).__name__
        d["__module__"] = type(value).__module__
        return d

    # Handle lists
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]

    # Handle dicts
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}

    # Handle primitives and other types
    return value


def serialize_message(message: Any) -> Any:
    """Helper to serialize messages for activity input.

    Adds type metadata (__type__, __module__) to dataclasses and Pydantic models
    to enable reconstruction on the receiving end. Handles nested ChatMessage
    and other objects with to_dict() methods.
    """
    return _serialize_value(message)


def deserialize_value(data: Any, type_registry: dict[str, type] | None = None) -> Any:
    """
    Attempt to deserialize a value using embedded type metadata.

    Args:
        data: The serialized data (could be dict with __type__ metadata)
        type_registry: Optional dict mapping type names to types for reconstruction

    Returns:
        Reconstructed object if type metadata found and type available, otherwise original data
    """
    if not isinstance(data, dict):
        return data

    type_name = data.get("__type__")
    module_name = data.get("__module__")

    # Special handling for MAF types with nested objects
    if type_name == "AgentExecutorRequest" or ("messages" in data and "should_respond" in data):
        try:
            return reconstruct_agent_executor_request(data)
        except Exception:
            pass

    if type_name == "AgentExecutorResponse" or ("executor_id" in data and "agent_run_response" in data):
        try:
            return reconstruct_agent_executor_response(data)
        except Exception:
            pass

    if not type_name:
        return data

    # Try to find the type
    target_type = None

    # First check the registry
    if type_registry and type_name in type_registry:
        target_type = type_registry[type_name]
    else:
        # Try to import from module
        if module_name:
            try:
                import importlib

                module = importlib.import_module(module_name)
                target_type = getattr(module, type_name, None)
            except Exception:
                pass

    if target_type:
        # Remove metadata before reconstruction
        clean_data = {k: v for k, v in data.items() if not k.startswith("__")}
        try:
            if is_dataclass(target_type):
                return target_type(**clean_data)
            elif issubclass(target_type, BaseModel):
                return target_type(**clean_data)
        except Exception:
            pass

    return data


def reconstruct_agent_executor_request(data: dict[str, Any]) -> AgentExecutorRequest:
    """Helper to reconstruct AgentExecutorRequest from dict."""
    # Reconstruct ChatMessage objects in messages
    messages_data = data.get("messages", [])
    messages = [ChatMessage.from_dict(m) if isinstance(m, dict) else m for m in messages_data]

    return AgentExecutorRequest(messages=messages, should_respond=data.get("should_respond", True))


def reconstruct_agent_executor_response(data: dict[str, Any]) -> AgentExecutorResponse:
    """Helper to reconstruct AgentExecutorResponse from dict."""
    # Reconstruct AgentRunResponse
    arr_data = data.get("agent_run_response", {})

    agent_run_response = None
    if isinstance(arr_data, dict):
        # Use from_dict for proper reconstruction
        agent_run_response = AgentRunResponse.from_dict(arr_data)
    else:
        agent_run_response = arr_data

    # Reconstruct full_conversation
    fc_data = data.get("full_conversation", [])
    full_conversation = None
    if fc_data:
        full_conversation = [ChatMessage.from_dict(m) if isinstance(m, dict) else m for m in fc_data]

    return AgentExecutorResponse(
        executor_id=data["executor_id"], agent_run_response=agent_run_response, full_conversation=full_conversation
    )


def reconstruct_message_for_handler(data: Any, handler_types: dict[type, Any]) -> Any:
    """
    Attempt to reconstruct a message to match one of the handler's expected types.

    Args:
        data: The serialized message data (could be dict, str, etc.)
        handler_types: Dict of message types the handler can accept

    Returns:
        Reconstructed message if possible, otherwise the original data
    """
    if not isinstance(data, dict):
        return data

    # Try AgentExecutorResponse first - it needs special handling for nested objects
    if "executor_id" in data and "agent_run_response" in data:
        try:
            return reconstruct_agent_executor_response(data)
        except Exception:
            pass

    # Try AgentExecutorRequest - also needs special handling for nested ChatMessage objects
    if "messages" in data and "should_respond" in data:
        try:
            return reconstruct_agent_executor_request(data)
        except Exception:
            pass

    # Try deserialize_value which uses embedded type metadata (__type__, __module__)
    if "__type__" in data:
        deserialized = deserialize_value(data)
        if deserialized is not data:
            return deserialized

    # Try to match against handler types by checking dict keys vs dataclass fields
    # Filter out metadata keys when comparing
    data_keys = {k for k in data.keys() if not k.startswith("__")}
    for msg_type in handler_types.keys():
        if is_dataclass(msg_type):
            # Check if the dict keys match the dataclass fields
            field_names = {f.name for f in fields(msg_type)}
            if field_names == data_keys or field_names.issubset(data_keys):
                try:
                    # Remove metadata before constructing
                    clean_data = {k: v for k, v in data.items() if not k.startswith("__")}
                    return msg_type(**clean_data)
                except Exception:
                    pass

    return data
