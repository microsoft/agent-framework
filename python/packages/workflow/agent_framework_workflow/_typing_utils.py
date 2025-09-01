# Copyright (c) Microsoft. All rights reserved.

from typing import Any, Union, get_args, get_origin


def is_instance_of(data: Any, target_type: type) -> bool:
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
    if origin is Union:
        return any(is_instance_of(data, arg) for arg in args)

    # Case 3: target_type is a generic type
    if origin in [list, set]:
        return isinstance(data, origin) and all(is_instance_of(item, args[0]) for item in data)  # type: ignore

    # Case 4: target_type is a tuple
    if origin is tuple:
        if len(args) == 1 and args[0] is Ellipsis:  # Tuple[...] case
            return isinstance(data, tuple)
        return (
            isinstance(data, tuple)
            and len(data) == len(args)  # type: ignore
            and all(is_instance_of(item, arg) for item, arg in zip(data, args, strict=False))  # type: ignore
        )

    # Case 5: target_type is a dict
    if origin is dict:
        return isinstance(data, dict) and all(
            is_instance_of(key, args[0]) and is_instance_of(value, args[1])
            for key, value in data.items()  # type: ignore
        )

    # Fallback: if we reach here, we assume data is an instance of the target_type
    return isinstance(data, target_type)
