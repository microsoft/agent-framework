# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import base64
import logging
import pickle  # nosec  # noqa: S403
from typing import Any

from ..exceptions import WorkflowCheckpointException

"""Checkpoint encoding using JSON structure with pickle+base64 for arbitrary data.

This hybrid approach provides:
- Human-readable JSON structure for debugging and inspection of primitives and collections
- Full Python object fidelity via pickle for data values (non-JSON-native types)
- Base64 encoding to embed binary pickle data in JSON strings

SECURITY WARNING: Checkpoints use pickle for data serialization. Only load checkpoints
from trusted sources. Loading a malicious checkpoint file can execute arbitrary code.
"""


logger = logging.getLogger("agent_framework")

# Marker to identify pickled values in serialized JSON
_PICKLE_MARKER = "__pickled__"
_TYPE_MARKER = "__type__"

# Types that are natively JSON-serializable and don't need pickling
_JSON_NATIVE_TYPES = (str, int, float, bool, type(None))


def encode_checkpoint_value(value: Any) -> Any:
    """Encode a Python value for checkpoint storage.

    JSON-native types (str, int, float, bool, None) pass through unchanged.
    Collections (dict, list) are recursed with their values encoded.
    All other types (dataclasses, custom objects, datetime, etc.) are pickled
    and stored as base64-encoded strings.

    Args:
        value: Any Python value to encode.

    Returns:
        A JSON-serializable representation of the value.
    """
    return _encode(value)


def decode_checkpoint_value(value: Any) -> Any:
    """Decode a value from checkpoint storage.

    Reverses the encoding performed by encode_checkpoint_value.
    Pickled values (identified by _PICKLE_MARKER) are decoded and unpickled.

    WARNING: Only call this with trusted data. Pickle can execute
    arbitrary code during deserialization. The post-unpickle type verification
    detects accidental corruption or type mismatches, but cannot prevent
    arbitrary code execution from malicious pickle payloads.

    Args:
        value: A JSON-deserialized value from checkpoint storage.

    Returns:
        The original Python value.

    Raises:
        WorkflowCheckpointException: If the unpickled object's type doesn't match
            the recorded type, indicating corruption, or if the base64/pickle
            data is malformed.
    """
    return _decode(value)


def _encode(value: Any) -> Any:
    """Recursively encode a value for JSON storage."""
    # JSON-native types pass through
    if isinstance(value, _JSON_NATIVE_TYPES):
        return value

    # Recursively encode dict values (keys become strings)
    if isinstance(value, dict):
        return {str(k): _encode(v) for k, v in value.items()}  # type: ignore

    # Recursively encode list items (lists are JSON-native collections)
    if isinstance(value, list):
        return [_encode(item) for item in value]  # type: ignore

    # Everything else (tuples, sets, dataclasses, custom objects, etc.): pickle and base64 encode
    return {
        _PICKLE_MARKER: _pickle_to_base64(value),
        _TYPE_MARKER: _type_to_key(type(value)),  # type: ignore
    }


def _decode(value: Any) -> Any:
    """Recursively decode a value from JSON storage."""
    # JSON-native types pass through
    if isinstance(value, _JSON_NATIVE_TYPES):
        return value

    # Handle encoded dicts
    if isinstance(value, dict):
        # Pickled value: decode, unpickle, and verify type
        if _PICKLE_MARKER in value and _TYPE_MARKER in value:
            obj = _base64_to_unpickle(value[_PICKLE_MARKER])  # type: ignore
            _verify_type(obj, value.get(_TYPE_MARKER))  # type: ignore
            return obj

        # Regular dict: decode values recursively
        return {k: _decode(v) for k, v in value.items()}  # type: ignore

    # Handle encoded lists
    if isinstance(value, list):
        return [_decode(item) for item in value]  # type: ignore

    return value


def _verify_type(obj: Any, expected_type_key: str) -> None:
    """Verify that an unpickled object matches its recorded type.

    This is a post-deserialization integrity check that detects accidental
    corruption or type mismatches. It does not prevent arbitrary code execution
    from malicious pickle payloads, since ``pickle.loads()`` has already
    executed by the time this function is called.

    Args:
        obj: The unpickled object.
        expected_type_key: The recorded type key (module:qualname format).

    Raises:
        WorkflowCheckpointException: If the types don't match.
    """
    actual_type_key = _type_to_key(type(obj))  # type: ignore
    if actual_type_key != expected_type_key:
        raise WorkflowCheckpointException(
            f"Type mismatch during checkpoint decoding: "
            f"expected '{expected_type_key}', got '{actual_type_key}'. "
            f"The checkpoint may be corrupted or tampered with."
        )


def _pickle_to_base64(value: Any) -> str:
    """Pickle a value and encode as base64 string."""
    pickled = pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
    return base64.b64encode(pickled).decode("ascii")


def _base64_to_unpickle(encoded: str) -> Any:
    """Decode base64 string and unpickle.

    Raises:
        WorkflowCheckpointException: If the base64 data is corrupted or the pickle
            format is incompatible.
    """
    try:
        pickled = base64.b64decode(encoded.encode("ascii"))
        return pickle.loads(pickled)  # nosec  # noqa: S301
    except Exception as exc:
        raise WorkflowCheckpointException(f"Failed to decode pickled checkpoint data: {exc}") from exc


def _type_to_key(t: type) -> str:
    """Convert a type to a module:qualname string."""
    return f"{t.__module__}:{t.__qualname__}"
