# Copyright (c) Microsoft. All rights reserved.

from typing import Any

from pydantic import BaseModel

# TODO (dmytrostruk): Resolve type errors


def make_hashable(input: Any, visited: Any = None) -> Any:
    """Recursively convert unhashable types to hashable equivalents.

    Args:
        input: The input to convert to a hashable type.
        visited: A dictionary of visited objects to prevent infinite recursion.

    Returns:
        Any: The input converted to a hashable type.
    """
    if visited is None:
        visited = {}

    # If we've seen this object before, return the stored placeholder or final result
    unique_obj_id = id(input)
    if unique_obj_id in visited:
        return visited[unique_obj_id]

    # Handle Pydantic models by manually traversing fields
    if isinstance(input, BaseModel):
        visited[unique_obj_id] = None
        data: Any = {}
        for field_name in input.model_fields:  # type: ignore
            value = getattr(input, field_name)
            data[field_name] = make_hashable(value, visited)
        result = tuple(sorted(data.items()))
        visited[unique_obj_id] = result
        return result

    # Convert dictionaries
    if isinstance(input, dict):
        visited[unique_obj_id] = None
        items: tuple[tuple[Any, Any], ...] = tuple(sorted((k, make_hashable(v, visited)) for k, v in input.items()))  # type: ignore
        visited[unique_obj_id] = items
        return items

    # Convert lists, sets, and tuples to tuples
    if isinstance(input, (list, set, tuple)):
        visited[unique_obj_id] = None
        items = tuple(make_hashable(item, visited) for item in input)  # type: ignore
        visited[unique_obj_id] = items
        return items

    # If it's already something hashable, just return it
    return input
