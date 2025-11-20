# Copyright (c) Microsoft. All rights reserved.

from typing import Any

from .._serialization import SerializationProtocol


def encode_value(value: Any) -> Any:
    """Recursively encode values for JSON-friendly serialization."""
    if isinstance(value, SerializationProtocol):
        return value.to_dict()
    if isinstance(value, dict):
        return {k: encode_value(v) for k, v in value.items()}  # type: ignore[misc]
    if isinstance(value, (list, tuple, set)):
        return [encode_value(v) for v in value]  # type: ignore[misc]
    return value
