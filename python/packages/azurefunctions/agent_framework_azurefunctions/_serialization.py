# Copyright (c) Microsoft. All rights reserved.

"""Serialization and deserialization utilities for workflow execution.

This module provides helper functions for serializing and deserializing messages,
dataclasses, and Pydantic models for cross-activity communication in Azure Functions.
"""

from __future__ import annotations

import logging
import types
from dataclasses import asdict, fields, is_dataclass
from typing import Any, Union, get_args, get_origin

from agent_framework import (
    AgentExecutorRequest,
    AgentExecutorResponse,
    AgentResponse,
    ChatMessage,
)
from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ============================================================================
# Serialization
# ============================================================================


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


# ============================================================================
# Deserialization
# ============================================================================


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

    if type_name == "AgentExecutorResponse" or ("executor_id" in data and "agent_response" in data):
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


# ============================================================================
# MAF Type Reconstruction
# ============================================================================


def reconstruct_agent_executor_request(data: dict[str, Any]) -> AgentExecutorRequest:
    """Helper to reconstruct AgentExecutorRequest from dict."""
    # Reconstruct ChatMessage objects in messages
    messages_data = data.get("messages", [])
    messages = [ChatMessage.from_dict(m) if isinstance(m, dict) else m for m in messages_data]

    return AgentExecutorRequest(messages=messages, should_respond=data.get("should_respond", True))


def reconstruct_agent_executor_response(data: dict[str, Any]) -> AgentExecutorResponse:
    """Helper to reconstruct AgentExecutorResponse from dict."""
    # Reconstruct AgentResponse
    arr_data = data.get("agent_response", {})
    agent_response = AgentResponse.from_dict(arr_data) if isinstance(arr_data, dict) else arr_data

    # Reconstruct full_conversation
    fc_data = data.get("full_conversation", [])
    full_conversation = None
    if fc_data:
        full_conversation = [ChatMessage.from_dict(m) if isinstance(m, dict) else m for m in fc_data]

    return AgentExecutorResponse(
        executor_id=data["executor_id"], agent_response=agent_response, full_conversation=full_conversation
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
    if "executor_id" in data and "agent_response" in data:
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
