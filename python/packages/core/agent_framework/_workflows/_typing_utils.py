# Copyright (c) Microsoft. All rights reserved.

import logging
from dataclasses import fields, is_dataclass
from types import UnionType
from typing import Any, TypeVar, Union, cast, get_args, get_origin

logger = logging.getLogger(__name__)

T = TypeVar("T")


def _coerce_to_type(value: Any, target_type: type[T]) -> T | None:
    """Best-effort conversion of value into target_type.

    Args:
        value: The value to convert (can be dict, dataclass, or object with __dict__)
        target_type: The target type to convert to

    Returns:
        Instance of target_type if conversion succeeds, None otherwise
    """
    if isinstance(value, target_type):
        return value  # type: ignore[return-value]

    # Convert dataclass instances or objects with __dict__ into dict first
    value_as_dict: dict[str, Any]
    if not isinstance(value, dict):
        if is_dataclass(value):
            value_as_dict = {f.name: getattr(value, f.name) for f in fields(value)}
        else:
            value_dict = getattr(value, "__dict__", None)
            if isinstance(value_dict, dict):
                value_as_dict = cast(dict[str, Any], value_dict)
            else:
                return None
    else:
        value_as_dict = cast(dict[str, Any], value)

    # Try to construct the target type from the dict
    ctor_kwargs: dict[str, Any] = dict(value_as_dict)

    if is_dataclass(target_type):
        field_names = {f.name for f in fields(target_type)}
        ctor_kwargs = {k: v for k, v in value_as_dict.items() if k in field_names}

    try:
        return target_type(**ctor_kwargs)  # type: ignore[call-arg,return-value]
    except TypeError as exc:
        logger.debug(f"_coerce_to_type could not call {target_type.__name__}(**..): {exc}")
    except Exception as exc:  # pragma: no cover - unexpected constructor failure
        logger.warning(
            f"_coerce_to_type encountered unexpected error calling {target_type.__name__} constructor: {exc}"
        )

    # Fallback: try to create instance without __init__ and set attributes
    try:
        instance = object.__new__(target_type)
    except Exception as exc:  # pragma: no cover - pathological type
        logger.debug(f"_coerce_to_type could not allocate {target_type.__name__} without __init__: {exc}")
        return None

    for key, val in value_as_dict.items():
        try:
            setattr(instance, key, val)
        except Exception as exc:
            logger.debug(
                f"_coerce_to_type could not set {target_type.__name__}.{key} during fallback assignment: {exc}"
            )
            continue
    return instance  # type: ignore[return-value]


def is_instance_of(data: Any, target_type: type | UnionType | Any) -> bool:
    """Check if the data is an instance of the target type.

    Args:
        data (Any): The data to check.
        target_type (type): The type to check against.

    Returns:
        bool: True if data is an instance of target_type, False otherwise.
    """
    # Case 0: target_type is Any - always return True
    if target_type is Any:
        return True

    origin = get_origin(target_type)
    args = get_args(target_type)

    # Case 1: origin is None, meaning target_type is not a generic type
    if origin is None:
        return isinstance(data, target_type)

    # Case 2: target_type is Optional[T] or Union[T1, T2, ...]
    # Optional[T] is really just as Union[T, None]
    if origin is UnionType:
        return any(is_instance_of(data, arg) for arg in args)

    # Case 2b: Handle typing.Union (legacy Union syntax)
    if origin is Union:
        return any(is_instance_of(data, arg) for arg in args)

    # Case 3: target_type is a generic type
    if origin in [list, set]:
        return isinstance(data, origin) and (
            not args or all(any(is_instance_of(item, arg) for arg in args) for item in data)  # type: ignore[misc]
        )  # type: ignore

    # Case 4: target_type is a tuple
    if origin is tuple:
        if len(args) == 2 and args[1] is Ellipsis:  # Tuple[T, ...] case
            element_type = args[0]
            return isinstance(data, tuple) and all(is_instance_of(item, element_type) for item in data)  # type: ignore[misc]
        if len(args) == 1 and args[0] is Ellipsis:  # Tuple[...] case
            return isinstance(data, tuple)
        if len(args) == 0:
            return isinstance(data, tuple)
        return (
            isinstance(data, tuple)
            and len(data) == len(args)  # type: ignore
            and all(is_instance_of(item, arg) for item, arg in zip(data, args, strict=False))  # type: ignore
        )

    # Case 5: target_type is a dict
    if origin is dict:
        return isinstance(data, dict) and (
            not args
            or all(
                is_instance_of(key, args[0]) and is_instance_of(value, args[1])
                for key, value in data.items()  # type: ignore
            )
        )

    # Case 6: Other custom generic classes - check origin type only
    # For generic classes, we check if data is an instance of the origin type
    # We don't validate the generic parameters at runtime since that's handled by type system
    if origin and hasattr(origin, "__name__"):
        return isinstance(data, origin)

    # Fallback: if we reach here, we assume data is an instance of the target_type
    return isinstance(data, target_type)


def serialize_type(t: type) -> str:
    """Serialize a type to a string.

    For example,

    serialize_type(int) => "builtins.int"
    """
    return f"{t.__module__}.{t.__qualname__}"


def deserialize_type(serialized_type_string: str) -> type:
    """Deserialize a serialized type string.

    For example,

    deserialize_type("builtins.int") => int
    """
    import importlib

    module_name, _, type_name = serialized_type_string.rpartition(".")
    module = importlib.import_module(module_name)

    return cast(type, getattr(module, type_name))


def is_type_compatible(source_type: type | UnionType | Any, target_type: type | UnionType | Any) -> bool:
    """Check if source_type is compatible with target_type.

    A type is compatible if values of source_type can be assigned to variables of target_type.
    For example:
    - list[ChatMessage] is compatible with list[str | ChatMessage]
    - str is compatible with str | int
    - int is compatible with Any

    Args:
        source_type: The type being assigned from
        target_type: The type being assigned to

    Returns:
        bool: True if source_type is compatible with target_type, False otherwise
    """
    # Case 0: target_type is Any - always compatible
    if target_type is Any:
        return True

    # Case 1: exact type match
    if source_type == target_type:
        return True

    source_origin = get_origin(source_type)
    source_args = get_args(source_type)
    target_origin = get_origin(target_type)
    target_args = get_args(target_type)

    # Case 2: target is Union/Optional - source is compatible if it matches any target member
    if target_origin is Union or target_origin is UnionType:
        # Special case: if source is also a Union, check that each source member
        # is compatible with at least one target member
        if source_origin is Union or source_origin is UnionType:
            return all(
                any(is_type_compatible(source_arg, target_arg) for target_arg in target_args)
                for source_arg in source_args
            )
        # If source is not a Union, check if it's compatible with any target member
        return any(is_type_compatible(source_type, arg) for arg in target_args)

    # Case 3: source is Union (and target is not Union) - each source member must be compatible with target
    if source_origin is Union or source_origin is UnionType:
        return all(is_type_compatible(arg, target_type) for arg in source_args)

    # Case 4: both are non-generic types
    if source_origin is None and target_origin is None:
        # Only call issubclass if both are actual types, not UnionType or Any
        if isinstance(source_type, type) and isinstance(target_type, type):
            try:
                return issubclass(source_type, target_type)
            except TypeError:
                # Handle cases where issubclass doesn't work (e.g., with special forms)
                return False
        return source_type == target_type

    # Case 5: different container types are not compatible
    if source_origin != target_origin:
        return False

    # Case 6: same container type - check generic arguments
    if source_origin in [list, set]:
        if not source_args and not target_args:
            return True  # Both are untyped
        if not source_args or not target_args:
            return True  # One is untyped - assume compatible
        # For collections, source element type must be compatible with target element type
        return is_type_compatible(source_args[0], target_args[0])

    # Case 7: tuple compatibility
    if source_origin is tuple:
        if not source_args and not target_args:
            return True  # Both are untyped tuples
        if not source_args or not target_args:
            return True  # One is untyped - assume compatible

        # Handle Tuple[T, ...] (variable length)
        if len(source_args) == 2 and source_args[1] is Ellipsis:
            if len(target_args) == 2 and target_args[1] is Ellipsis:
                return is_type_compatible(source_args[0], target_args[0])
            return False  # Variable length can't be assigned to fixed length

        if len(target_args) == 2 and target_args[1] is Ellipsis:
            # Fixed length can be assigned to variable length if element types are compatible
            return all(is_type_compatible(source_arg, target_args[0]) for source_arg in source_args)

        # Fixed length tuples must have same length and compatible element types
        if len(source_args) != len(target_args):
            return False
        return all(is_type_compatible(s_arg, t_arg) for s_arg, t_arg in zip(source_args, target_args, strict=False))

    # Case 8: dict compatibility
    if source_origin is dict:
        if not source_args and not target_args:
            return True  # Both are untyped dicts
        if not source_args or not target_args:
            return True  # One is untyped - assume compatible
        if len(source_args) != 2 or len(target_args) != 2:
            return False  # Malformed dict types
        # Both key and value types must be compatible
        return is_type_compatible(source_args[0], target_args[0]) and is_type_compatible(source_args[1], target_args[1])

    # Case 9: custom generic classes - check if origins are the same and args are compatible
    if source_origin and target_origin and source_origin == target_origin:
        if not source_args and not target_args:
            return True  # Both are untyped generics
        if not source_args or not target_args:
            return True  # One is untyped - assume compatible
        if len(source_args) != len(target_args):
            return False  # Different number of type parameters
        return all(is_type_compatible(s_arg, t_arg) for s_arg, t_arg in zip(source_args, target_args, strict=False))

    # Case 10: fallback - check if source is subclass of target (for non-generic types)
    if source_origin is None and target_origin is None:
        try:
            # Only call issubclass if both are actual types, not UnionType or Any
            if isinstance(source_type, type) and isinstance(target_type, type):
                return issubclass(source_type, target_type)
            return source_type == target_type
        except TypeError:
            return False

    return False
