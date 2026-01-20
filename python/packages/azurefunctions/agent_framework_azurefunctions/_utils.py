# Copyright (c) Microsoft. All rights reserved.

"""Utility functions for workflow execution.

This module provides helper functions for serialization, deserialization, and
context management used by the workflow orchestrator and executors.
"""

from __future__ import annotations

import asyncio
import logging
import types
from dataclasses import asdict, fields, is_dataclass
from typing import Any, Union, get_args, get_origin

from agent_framework import (
    AgentExecutorRequest,
    AgentExecutorResponse,
    AgentRunResponse,
    ChatMessage,
    CheckpointStorage,
    Message,
    RequestInfoEvent,
    RunnerContext,
    SharedState,
    WorkflowCheckpoint,
    WorkflowEvent,
)
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class CapturingRunnerContext(RunnerContext):
    """A RunnerContext implementation that captures messages and events for Azure Functions activities.

    This context is designed for executing standard Executors within Azure Functions activities.
    It captures all messages and events produced during execution without requiring durable
    entity storage, allowing the results to be returned to the orchestrator.

    Unlike the full InProcRunnerContext, this implementation:
    - Does NOT support checkpointing (always returns False for has_checkpointing)
    - Does NOT support streaming (always returns False for is_streaming)
    - Captures messages and events in memory for later retrieval

    The orchestrator manages state coordination; this context just captures execution output.
    """

    def __init__(self) -> None:
        """Initialize the capturing runner context."""
        self._messages: dict[str, list[Message]] = {}
        self._event_queue: asyncio.Queue[WorkflowEvent] = asyncio.Queue()
        self._pending_request_info_events: dict[str, RequestInfoEvent] = {}
        self._workflow_id: str | None = None
        self._streaming: bool = False

    # region Messaging

    async def send_message(self, message: Message) -> None:
        """Capture a message sent by an executor."""
        self._messages.setdefault(message.source_id, [])
        self._messages[message.source_id].append(message)

    async def drain_messages(self) -> dict[str, list[Message]]:
        """Drain and return all captured messages."""
        from copy import copy

        messages = copy(self._messages)
        self._messages.clear()
        return messages

    async def has_messages(self) -> bool:
        """Check if there are any captured messages."""
        return bool(self._messages)

    # endregion Messaging

    # region Events

    async def add_event(self, event: WorkflowEvent) -> None:
        """Capture an event produced during execution."""
        await self._event_queue.put(event)

    async def drain_events(self) -> list[WorkflowEvent]:
        """Drain all currently queued events without blocking."""
        events: list[WorkflowEvent] = []
        while True:
            try:
                events.append(self._event_queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return events

    async def has_events(self) -> bool:
        """Check if there are any queued events."""
        return not self._event_queue.empty()

    async def next_event(self) -> WorkflowEvent:
        """Wait for and return the next event."""
        return await self._event_queue.get()

    # endregion Events

    # region Checkpointing (not supported in activity context)

    def has_checkpointing(self) -> bool:
        """Checkpointing is not supported in activity context."""
        return False

    def set_runtime_checkpoint_storage(self, storage: CheckpointStorage) -> None:
        """No-op: checkpointing not supported in activity context."""
        pass

    def clear_runtime_checkpoint_storage(self) -> None:
        """No-op: checkpointing not supported in activity context."""
        pass

    async def create_checkpoint(
        self,
        shared_state: SharedState,
        iteration_count: int,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Checkpointing not supported in activity context."""
        raise NotImplementedError("Checkpointing is not supported in Azure Functions activity context")

    async def load_checkpoint(self, checkpoint_id: str) -> WorkflowCheckpoint | None:
        """Checkpointing not supported in activity context."""
        raise NotImplementedError("Checkpointing is not supported in Azure Functions activity context")

    async def apply_checkpoint(self, checkpoint: WorkflowCheckpoint) -> None:
        """Checkpointing not supported in activity context."""
        raise NotImplementedError("Checkpointing is not supported in Azure Functions activity context")

    # endregion Checkpointing

    # region Workflow Configuration

    def set_workflow_id(self, workflow_id: str) -> None:
        """Set the workflow ID."""
        self._workflow_id = workflow_id

    def reset_for_new_run(self) -> None:
        """Reset the context for a new run."""
        self._messages.clear()
        self._event_queue = asyncio.Queue()
        self._pending_request_info_events.clear()
        self._streaming = False

    def set_streaming(self, streaming: bool) -> None:
        """Set streaming mode (not used in activity context)."""
        self._streaming = streaming

    def is_streaming(self) -> bool:
        """Check if streaming mode is enabled (always False in activity context)."""
        return self._streaming

    # endregion Workflow Configuration

    # region Request Info Events

    async def add_request_info_event(self, event: RequestInfoEvent) -> None:
        """Add a RequestInfoEvent and track it for correlation."""
        self._pending_request_info_events[event.request_id] = event
        await self.add_event(event)

    async def send_request_info_response(self, request_id: str, response: Any) -> None:
        """Send a response correlated to a pending request.

        Note: This is not supported in activity context since human-in-the-loop
        scenarios require orchestrator-level coordination.
        """
        raise NotImplementedError(
            "send_request_info_response is not supported in Azure Functions activity context. "
            "Human-in-the-loop scenarios should be handled at the orchestrator level."
        )

    async def get_pending_request_info_events(self) -> dict[str, RequestInfoEvent]:
        """Get the mapping of request IDs to their corresponding RequestInfoEvent."""
        return dict(self._pending_request_info_events)

    # endregion Request Info Events


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
    """Attempt to deserialize a value using embedded type metadata.

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
            logger.debug("Could not reconstruct as AgentExecutorRequest, trying next strategy")

    if type_name == "AgentExecutorResponse" or ("executor_id" in data and "agent_run_response" in data):
        try:
            return reconstruct_agent_executor_response(data)
        except Exception:
            logger.debug("Could not reconstruct as AgentExecutorResponse, trying next strategy")

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
                logger.debug("Could not import module %s for type %s", module_name, type_name)

    if target_type:
        # Remove metadata before reconstruction
        clean_data = {k: v for k, v in data.items() if not k.startswith("__")}
        try:
            if is_dataclass(target_type) or issubclass(target_type, BaseModel):
                return target_type(**clean_data)
        except Exception:
            logger.debug("Could not reconstruct type %s from data", type_name)

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
    agent_run_response = AgentRunResponse.from_dict(arr_data) if isinstance(arr_data, dict) else arr_data

    # Reconstruct full_conversation
    fc_data = data.get("full_conversation", [])
    full_conversation = None
    if fc_data:
        full_conversation = [ChatMessage.from_dict(m) if isinstance(m, dict) else m for m in fc_data]

    return AgentExecutorResponse(
        executor_id=data["executor_id"], agent_run_response=agent_run_response, full_conversation=full_conversation
    )


def reconstruct_message_for_handler(data: Any, input_types: list[type[Any]]) -> Any:
    """Attempt to reconstruct a message to match one of the handler's expected types.

    Handles:
    - Dicts with __type__ metadata -> reconstructs to original dataclass/Pydantic model
    - Lists (from fan-in) -> recursively reconstructs each item
    - Union types (T | U) -> tries each type in the union
    - AgentExecutorRequest/Response -> special handling for nested ChatMessage objects

    Args:
        data: The serialized message data (could be dict, str, list, etc.)
        input_types: List of message types the executor can accept

    Returns:
        Reconstructed message if possible, otherwise the original data
    """
    # Flatten union types in input_types (e.g., T | U becomes [T, U])
    flattened_types: list[type[Any]] = []
    for input_type in input_types:
        origin = get_origin(input_type)
        # Handle both typing.Union and types.UnionType (Python 3.10+ | syntax)
        if origin is Union or isinstance(input_type, types.UnionType):
            # This is a Union type (T | U), extract the component types
            flattened_types.extend(get_args(input_type))
        else:
            flattened_types.append(input_type)

    # Handle lists (fan-in aggregation) - recursively reconstruct each item
    if isinstance(data, list):
        # Extract element types from list[T] annotations in input_types if possible
        element_types: list[type[Any]] = []
        for input_type in input_types:
            origin = get_origin(input_type)
            if origin is list:
                args = get_args(input_type)
                if args:
                    # Handle union types inside list[T | U]
                    for arg in args:
                        arg_origin = get_origin(arg)
                        if arg_origin is Union or isinstance(arg, types.UnionType):
                            element_types.extend(get_args(arg))
                        else:
                            element_types.append(arg)

        # Recursively reconstruct each item in the list
        return [reconstruct_message_for_handler(item, element_types or flattened_types) for item in data]

    if not isinstance(data, dict):
        return data

    # Try AgentExecutorResponse first - it needs special handling for nested objects
    if "executor_id" in data and "agent_run_response" in data:
        try:
            return reconstruct_agent_executor_response(data)
        except Exception:
            logger.debug("Could not reconstruct as AgentExecutorResponse in handler context")

    # Try AgentExecutorRequest - also needs special handling for nested ChatMessage objects
    if "messages" in data and "should_respond" in data:
        try:
            return reconstruct_agent_executor_request(data)
        except Exception:
            logger.debug("Could not reconstruct as AgentExecutorRequest in handler context")

    # Try deserialize_value which uses embedded type metadata (__type__, __module__)
    if "__type__" in data:
        deserialized = deserialize_value(data)
        if deserialized is not data:
            return deserialized

    # Try to match against input types by checking dict keys vs dataclass fields
    # Filter out metadata keys when comparing
    data_keys = {k for k in data if not k.startswith("__")}
    for msg_type in flattened_types:
        if is_dataclass(msg_type):
            # Check if the dict keys match the dataclass fields
            field_names = {f.name for f in fields(msg_type)}
            if field_names == data_keys or field_names.issubset(data_keys):
                try:
                    # Remove metadata before constructing
                    clean_data = {k: v for k, v in data.items() if not k.startswith("__")}
                    return msg_type(**clean_data)
                except Exception:
                    logger.debug("Could not construct %s from matching fields", msg_type.__name__)

    return data
