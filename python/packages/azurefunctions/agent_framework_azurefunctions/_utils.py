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
            if is_dataclass(target_type):
                # Recursively reconstruct nested fields for dataclasses
                reconstructed_data = _reconstruct_dataclass_fields(target_type, clean_data)
                return target_type(**reconstructed_data)
            if issubclass(target_type, BaseModel):
                # Pydantic handles nested model validation automatically
                return target_type.model_validate(clean_data)
        except Exception:
            logger.debug("Could not reconstruct type %s from data", type_name)

    return data


def _reconstruct_dataclass_fields(dataclass_type: type, data: dict[str, Any]) -> dict[str, Any]:
    """Recursively reconstruct nested dataclass and Pydantic fields.

    This function processes each field of a dataclass, looking up the expected type
    from type hints and reconstructing nested objects (dataclasses, Pydantic models, lists).

    Args:
        dataclass_type: The dataclass type being constructed
        data: The dict of field values

    Returns:
        Dict with nested objects properly reconstructed
    """
    if not is_dataclass(dataclass_type):
        return data

    result = {}
    type_hints = {}

    # Get type hints for the dataclass
    try:
        import typing

        type_hints = typing.get_type_hints(dataclass_type)
    except Exception:
        # Fall back to field annotations if get_type_hints fails
        for f in fields(dataclass_type):
            type_hints[f.name] = f.type

    for key, value in data.items():
        if key not in type_hints:
            result[key] = value
            continue

        field_type = type_hints[key]

        # Handle Optional types (Union with None)
        origin = get_origin(field_type)
        if origin is Union or isinstance(field_type, types.UnionType):
            args = get_args(field_type)
            # Filter out NoneType to get the actual type
            non_none_types = [t for t in args if t is not type(None)]
            if len(non_none_types) == 1:
                field_type = non_none_types[0]

        # Recursively reconstruct the value
        result[key] = _reconstruct_typed_value(value, field_type)

    return result


def _reconstruct_typed_value(value: Any, target_type: type) -> Any:
    """Reconstruct a single value to the target type.

    Handles dataclasses, Pydantic models, and lists with typed elements.

    Args:
        value: The value to reconstruct
        target_type: The expected type

    Returns:
        The reconstructed value
    """
    if value is None:
        return None

    # If already the correct type, return as-is
    try:
        if isinstance(value, target_type):
            return value
    except TypeError:
        # target_type might not be a valid type for isinstance
        pass

    # Handle dict values that need reconstruction
    if isinstance(value, dict):
        # First try deserialize_value which uses embedded type metadata
        if "__type__" in value:
            deserialized = deserialize_value(value)
            if deserialized is not value:
                return deserialized

        # Handle Pydantic models
        if hasattr(target_type, "model_validate"):
            try:
                return target_type.model_validate(value)
            except Exception:
                logger.debug("Could not validate Pydantic model %s", target_type)

        # Handle dataclasses
        if is_dataclass(target_type) and isinstance(target_type, type):
            try:
                # Recursively reconstruct nested fields
                reconstructed = _reconstruct_dataclass_fields(target_type, value)
                return target_type(**reconstructed)
            except Exception:
                logger.debug("Could not construct dataclass %s", target_type)

    # Handle list values
    if isinstance(value, list):
        origin = get_origin(target_type)
        if origin is list:
            args = get_args(target_type)
            if args:
                element_type = args[0]
                return [_reconstruct_typed_value(item, element_type) for item in value]

    return value


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
                    # Recursively reconstruct nested objects based on field types
                    reconstructed_data = _reconstruct_dataclass_fields(msg_type, clean_data)
                    return msg_type(**reconstructed_data)
                except Exception:
                    logger.debug("Could not construct %s from matching fields", msg_type.__name__)

    return data


# ============================================================================
# HITL Response Handler Execution
# ============================================================================


async def _execute_hitl_response_handler(
    executor: Any,
    hitl_message: dict[str, Any],
    shared_state: SharedState,
    runner_context: CapturingRunnerContext,
) -> None:
    """Execute a HITL response handler on an executor.

    This function handles the delivery of a HITL response to the executor's
    @response_handler method. It:
    1. Deserializes the original request and response
    2. Finds the matching response handler based on types
    3. Creates a WorkflowContext and invokes the handler

    Args:
        executor: The executor instance that has a @response_handler
        hitl_message: The HITL response message containing original_request and response
        shared_state: The shared state for the workflow context
        runner_context: The runner context for capturing outputs
    """
    from agent_framework._workflows._workflow_context import WorkflowContext

    # Extract the response data
    original_request_data = hitl_message.get("original_request")
    response_data = hitl_message.get("response")
    response_type_str = hitl_message.get("response_type")

    # Deserialize the original request
    original_request = deserialize_value(original_request_data)

    # Deserialize the response - try to match expected type
    response = _deserialize_hitl_response(response_data, response_type_str)

    # Find the matching response handler
    handler = executor._find_response_handler(original_request, response)

    if handler is None:
        logger.warning(
            "No response handler found for HITL response in executor %s. Request type: %s, Response type: %s",
            executor.id,
            type(original_request).__name__,
            type(response).__name__,
        )
        return

    # Create a WorkflowContext for the handler
    # Use a special source ID to indicate this is a HITL response
    ctx = WorkflowContext(
        executor=executor,
        source_executor_ids=["__hitl_response__"],
        runner_context=runner_context,
        shared_state=shared_state,
    )

    # Call the response handler
    # Note: handler is already a partial with original_request bound
    logger.debug(
        "Invoking response handler for HITL request in executor %s",
        executor.id,
    )
    await handler(response, ctx)


def _deserialize_hitl_response(response_data: Any, response_type_str: str | None) -> Any:
    """Deserialize a HITL response to its expected type.

    Args:
        response_data: The raw response data (typically a dict from JSON)
        response_type_str: The fully qualified type name (module:classname)

    Returns:
        The deserialized response, or the original data if deserialization fails
    """
    logger.debug(
        "Deserializing HITL response. response_type_str=%s, response_data type=%s",
        response_type_str,
        type(response_data).__name__,
    )

    if response_data is None:
        return None

    # If already a primitive, return as-is
    if not isinstance(response_data, dict):
        logger.debug("Response data is not a dict, returning as-is: %s", type(response_data).__name__)
        return response_data

    # Try to deserialize using the type hint
    if response_type_str:
        try:
            module_name, class_name = response_type_str.rsplit(":", 1)
            import importlib

            module = importlib.import_module(module_name)
            response_type = getattr(module, class_name, None)

            if response_type:
                logger.debug("Found response type %s, attempting reconstruction", response_type)
                # Use the shared reconstruction logic which handles nested objects
                result = _reconstruct_typed_value(response_data, response_type)
                logger.debug("Reconstructed response type: %s", type(result).__name__)
                return result
            logger.warning("Could not find class %s in module %s", class_name, module_name)

        except Exception as e:
            logger.warning("Could not deserialize HITL response to %s: %s", response_type_str, e)

    # Fall back to generic deserialization
    logger.debug("Falling back to generic deserialization")
    return deserialize_value(response_data)
