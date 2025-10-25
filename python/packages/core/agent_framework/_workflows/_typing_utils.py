# Copyright (c) Microsoft. All rights reserved.

import logging
from dataclasses import fields, is_dataclass
from types import UnionType
from typing import Any, Union, cast, get_args, get_origin

logger = logging.getLogger(__name__)


def _coerce_to_type(value: Any, target_type: type) -> Any | None:
    """Best-effort conversion of value into target_type."""
    if isinstance(value, target_type):
        return value

    # Convert dataclass instances or objects with __dict__ into dict first
    if not isinstance(value, dict):
        if is_dataclass(value):
            value = {f.name: getattr(value, f.name) for f in fields(value)}
        else:
            value_dict = getattr(value, "__dict__", None)
            if isinstance(value_dict, dict):
                value = dict(value_dict)

    if isinstance(value, dict):
        ctor_kwargs: dict[str, Any] = dict(value)

        if is_dataclass(target_type):
            field_names = {f.name for f in fields(target_type)}
            ctor_kwargs = {k: v for k, v in value.items() if k in field_names}

        try:
            return target_type(**ctor_kwargs)  # type: ignore[arg-type]
        except TypeError as exc:
            logger.debug(f"_coerce_to_type could not call {target_type.__name__}(**..): {exc}")
        except Exception as exc:  # pragma: no cover - unexpected constructor failure
            logger.warning(
                f"_coerce_to_type encountered unexpected error calling {target_type.__name__} constructor: {exc}"
            )
        try:
            instance: Any = object.__new__(target_type)
        except Exception as exc:  # pragma: no cover - pathological type
            logger.debug(f"_coerce_to_type could not allocate {target_type.__name__} without __init__: {exc}")
            return None
        for key, val in value.items():
            try:
                setattr(instance, key, val)
            except Exception as exc:
                logger.debug(
                    f"_coerce_to_type could not set {target_type.__name__}.{key} during fallback assignment: {exc}"
                )
                continue
        return instance

    return None


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
            not args or all(any(is_instance_of(item, arg) for arg in args) for item in data)
        )  # type: ignore

    # Case 4: target_type is a tuple
    if origin is tuple:
        if len(args) == 2 and args[1] is Ellipsis:  # Tuple[T, ...] case
            element_type = args[0]
            return isinstance(data, tuple) and all(is_instance_of(item, element_type) for item in data)
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
