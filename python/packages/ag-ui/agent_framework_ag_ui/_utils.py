# Copyright (c) Microsoft. All rights reserved.

"""Utility functions for AG-UI integration."""

import copy
import uuid
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from typing import Any


def generate_event_id() -> str:
    """Generate a unique event ID."""
    return str(uuid.uuid4())


def merge_state(current: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    """Merge state updates.

    Args:
        current: Current state dictionary
        update: Update to apply

    Returns:
        Merged state
    """
    result = copy.deepcopy(current)
    result.update(update)
    return result


def make_json_safe(obj: Any) -> Any:  # noqa: ANN401
    """Make an object JSON serializable.

    Args:
        obj: Object to make JSON safe

    Returns:
        JSON-serializable version of the object
    """
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if is_dataclass(obj):
        return asdict(obj)  # type: ignore[arg-type]
    if hasattr(obj, "model_dump"):
        return obj.model_dump()  # type: ignore[no-any-return]
    if hasattr(obj, "dict"):
        return obj.dict()  # type: ignore[no-any-return]
    if hasattr(obj, "__dict__"):
        return {key: make_json_safe(value) for key, value in vars(obj).items()}  # type: ignore[misc]
    if isinstance(obj, (list, tuple)):
        return [make_json_safe(item) for item in obj]  # type: ignore[misc]
    if isinstance(obj, dict):
        return {key: make_json_safe(value) for key, value in obj.items()}  # type: ignore[misc]
    return str(obj)
