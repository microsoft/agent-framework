# Copyright (c) Microsoft. All rights reserved.

"""Serialization utilities for workflow execution.

This module provides thin wrappers around the core checkpoint encoding system
(encode_checkpoint_value / decode_checkpoint_value) from agent_framework._workflows.

The core checkpoint encoding uses pickle + base64 for type-safe roundtripping of
arbitrary Python objects (dataclasses, Pydantic models, Message, etc.) while
keeping JSON-native types (str, int, float, bool, None) as-is.

This module adds:
- serialize_value / deserialize_value: convenience aliases for encode/decode
- reconstruct_to_type: for HITL responses where external data (without type markers)
  needs to be reconstructed to a known type
- _resolve_type: resolves 'module:class' type keys to Python types
"""

from __future__ import annotations

import importlib
import logging
from dataclasses import is_dataclass
from typing import Any

from agent_framework._workflows._checkpoint_encoding import decode_checkpoint_value, encode_checkpoint_value

logger = logging.getLogger(__name__)


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

    Delegates to core checkpoint encoding which uses pickle + base64 for
    non-JSON-native types (dataclasses, Pydantic models, Message, etc.).

    Args:
        value: Any Python value (primitive, dataclass, Pydantic model, Message, etc.)

    Returns:
        A JSON-serializable representation with embedded type metadata for reconstruction.
    """
    return encode_checkpoint_value(value)


def deserialize_value(value: Any) -> Any:
    """Deserialize a value previously serialized with serialize_value().

    Delegates to core checkpoint decoding which unpickles base64-encoded values
    and verifies type integrity.

    Args:
        value: The serialized data (dict with pickle markers, list, or primitive)

    Returns:
        Reconstructed typed object if type metadata found, otherwise original value.
    """
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

    # Try decoding if data has pickle markers (from checkpoint encoding)
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
