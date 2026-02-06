# Copyright (c) Microsoft. All rights reserved.

"""Serialization utilities for workflow execution.

This module provides thin wrappers around the core checkpoint encoding system
(encode_checkpoint_value / decode_checkpoint_value) from agent_framework._workflows,
adding Pydantic model support.

The core checkpoint encoding handles type-safe roundtripping of:
- Objects with to_dict/from_dict (ChatMessage, AgentResponse, etc.)
- Dataclasses (AgentExecutorRequest/Response, custom dataclasses)
- Objects with to_json/from_json
- Primitives, lists, dicts

This module adds:
- serialize_value / deserialize_value: wrappers that also handle Pydantic BaseModel instances
- reconstruct_to_type: for HITL responses where external data (without type markers)
  needs to be reconstructed to a known type
"""

from __future__ import annotations

import importlib
import logging
from dataclasses import fields as dc_fields
from dataclasses import is_dataclass
from typing import Any

from agent_framework._workflows import decode_checkpoint_value, encode_checkpoint_value
from agent_framework._workflows._checkpoint_encoding import DATACLASS_MARKER, MODEL_MARKER
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Marker for Pydantic models serialized by this module.
# Core checkpoint encoding only supports to_dict/from_dict protocol; Pydantic v2
# uses model_dump/model_validate, so we handle it here with a compatible marker format.
PYDANTIC_MARKER = "__af_pydantic__"


def _resolve_type(type_key: str) -> type | None:
    """Resolve a 'module:class' type key to its Python type.

    Args:
        type_key: Fully qualified type reference in 'module_name:class_name' format.

    Returns:
        The resolved type, or None if resolution fails.
    """
    try:
        module_name, class_name = type_key.split(":", 1)
        module = importlib.import_module(module_name)
        return getattr(module, class_name, None)
    except Exception:
        logger.debug("Could not resolve type %s", type_key)
        return None


# ============================================================================
# Serialize / Deserialize
# ============================================================================


def serialize_value(value: Any) -> Any:
    """Serialize a value for JSON-compatible cross-activity communication.

    Extends core checkpoint encoding with Pydantic BaseModel support.
    The output is JSON-serializable and can be deserialized with deserialize_value().

    Dataclasses are handled here (rather than delegating to encode_checkpoint_value)
    because their fields may contain nested Pydantic models that core encoding
    does not recognise.

    Args:
        value: Any Python value (primitive, dataclass, Pydantic model, ChatMessage, etc.)

    Returns:
        A JSON-serializable representation with embedded type metadata for reconstruction.
    """
    if isinstance(value, BaseModel):
        cls = type(value)
        return {
            PYDANTIC_MARKER: f"{cls.__module__}:{cls.__name__}",
            "value": encode_checkpoint_value(value.model_dump()),
        }

    # Handle dataclasses ourselves so that nested Pydantic models get the
    # PYDANTIC_MARKER treatment instead of being str()'d by core encoding.
    if is_dataclass(value) and not isinstance(value, type):
        cls = type(value)
        return {
            DATACLASS_MARKER: f"{cls.__module__}:{cls.__name__}",
            **{field.name: serialize_value(getattr(value, field.name)) for field in dc_fields(value)},
        }

    # Handle lists and dicts recursively to catch nested Pydantic models
    if isinstance(value, list):
        return [serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {k: serialize_value(v) for k, v in value.items()}

    return encode_checkpoint_value(value)


def deserialize_value(value: Any) -> Any:
    """Deserialize a value previously serialized with serialize_value().

    Handles core checkpoint markers (__af_model__, __af_dataclass__) and
    Pydantic markers (__af_pydantic__) to reconstruct the original typed objects.

    Dataclasses are reconstructed here (rather than delegating to
    decode_checkpoint_value) so that fields containing PYDANTIC_MARKER dicts
    are properly deserialized.

    Args:
        value: The serialized data (dict with type markers, list, or primitive)

    Returns:
        Reconstructed typed object if type metadata found, otherwise original value.
    """
    if isinstance(value, dict):
        # Handle Pydantic marker
        if PYDANTIC_MARKER in value and "value" in value:
            type_key: str = value[PYDANTIC_MARKER]
            payload = decode_checkpoint_value(value["value"])
            cls = _resolve_type(type_key)
            if cls is not None and hasattr(cls, "model_validate"):
                try:
                    return cls.model_validate(payload)
                except Exception:
                    logger.debug("Could not reconstruct Pydantic model %s", type_key)
            return payload

        # Handle dataclass marker — deserialize fields ourselves so that nested
        # PYDANTIC_MARKER dicts are properly handled.
        if DATACLASS_MARKER in value:
            type_key = value[DATACLASS_MARKER]
            cls = _resolve_type(type_key)
            if cls is not None and is_dataclass(cls):
                try:
                    field_data = {k: deserialize_value(v) for k, v in value.items() if k != DATACLASS_MARKER}
                    return cls(**field_data)
                except Exception:
                    logger.debug("Could not reconstruct dataclass %s, falling back to core decode", type_key)
            return decode_checkpoint_value(value)

        # Handle model marker (to_dict/from_dict objects like ChatMessage) — core
        # handles these fully since the object's own serialisation manages nesting.
        if MODEL_MARKER in value:
            return decode_checkpoint_value(value)

        # Recurse into plain dicts to catch nested markers
        return {k: deserialize_value(v) for k, v in value.items()}

    if isinstance(value, list):
        return [deserialize_value(item) for item in value]

    return decode_checkpoint_value(value)


# ============================================================================
# HITL Type Reconstruction
# ============================================================================


def reconstruct_to_type(value: Any, target_type: type) -> Any:
    """Reconstruct a value to a known target type.

    Used for HITL responses where external data (without checkpoint type markers)
    needs to be reconstructed to a specific type determined by the response_type hint.

    Tries strategies in order:
    1. Return as-is if already the correct type
    2. deserialize_value (for data with any type markers)
    3. Pydantic model_validate (for Pydantic models)
    4. Dataclass constructor (for dataclasses)

    Args:
        value: The value to reconstruct (typically a dict from JSON)
        target_type: The expected type to reconstruct to

    Returns:
        Reconstructed value if possible, otherwise the original value
    """
    if value is None:
        return None

    try:
        if isinstance(value, target_type):
            return value
    except TypeError:
        pass

    if not isinstance(value, dict):
        return value

    # Try marker-based decoding if data has type markers
    if MODEL_MARKER in value or DATACLASS_MARKER in value or PYDANTIC_MARKER in value:
        decoded = deserialize_value(value)
        if not isinstance(decoded, dict):
            return decoded

    # Try Pydantic model validation (for unmarked dicts, e.g., external HITL data)
    if hasattr(target_type, "model_validate"):
        try:
            return target_type.model_validate(value)
        except Exception:
            logger.debug("Could not validate Pydantic model %s", target_type)

    # Try dataclass construction (for unmarked dicts, e.g., external HITL data)
    if is_dataclass(target_type) and isinstance(target_type, type):
        try:
            return target_type(**value)
        except Exception:
            logger.debug("Could not construct dataclass %s", target_type)

    return value
