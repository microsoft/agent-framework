# Copyright (c) Microsoft. All rights reserved.

import json
import re
from collections.abc import MutableMapping
from typing import Any, ClassVar, Protocol, TypeVar, runtime_checkable

from ._logging import get_logger

logger = get_logger()

TClass = TypeVar("TClass", bound="SerializationMixin")
TProtocol = TypeVar("TProtocol", bound="SerializationProtocol")

# Regex pattern for converting CamelCase to snake_case
_CAMEL_TO_SNAKE_PATTERN = re.compile(r"(?<!^)(?=[A-Z])")


@runtime_checkable
class SerializationProtocol(Protocol):
    """Protocol for objects that support serialization and deserialization."""

    def to_dict(self, **kwargs: Any) -> dict[str, Any]:
        """Convert the instance to a dictionary."""
        ...

    @classmethod
    def from_dict(cls: type[TProtocol], value: MutableMapping[str, Any], /, **kwargs: Any) -> TProtocol:
        """Create an instance from a dictionary."""
        ...


class SerializationMixin:
    """Mixin class providing serialization and deserialization capabilities.

    Classes using this mixin should handle MutableMapping inputs in their __init__ method
    for any parameters that expect SerializationMixin/SerializationProtocol instances.
    The __init__ should check if the value is a MutableMapping and call from_dict() to convert it.
    """

    DEFAULT_EXCLUDE: ClassVar[set[str]] = set()
    INJECTABLE: ClassVar[set[str]] = set()

    def to_dict(self, *, exclude: set[str] | None = None, exclude_none: bool = True) -> dict[str, Any]:
        """Convert the instance and any nested objects to a dictionary.

        Args:
            exclude: Set of field names to exclude from serialization.
            exclude_none: Whether to exclude None values from the output. Defaults to True.

        Returns:
            Dictionary representation of the instance.
        """
        # Combine exclude sets
        combined_exclude = set(self.DEFAULT_EXCLUDE)
        if exclude:
            combined_exclude.update(exclude)
        combined_exclude.update(self.INJECTABLE)

        # Get all instance attributes
        result: dict[str, Any] = {"type": self._get_type_identifier()}
        for key, value in self.__dict__.items():
            if key not in combined_exclude and not key.startswith("_"):
                if exclude_none and value is None:
                    continue
                # Recursively serialize SerializationProtocol objects
                if isinstance(value, SerializationProtocol):
                    result[key] = value.to_dict(exclude=exclude, exclude_none=exclude_none)
                # Handle lists containing SerializationProtocol objects
                elif isinstance(value, list):
                    result[key] = [
                        item.to_dict(exclude=exclude, exclude_none=exclude_none)
                        if isinstance(item, SerializationProtocol)
                        else item
                        for item in value
                    ]
                # Handle dicts containing SerializationProtocol values
                elif isinstance(value, dict):
                    serialized_dict = {}
                    for k, v in value.items():
                        if isinstance(v, SerializationProtocol):
                            serialized_dict[k] = v.to_dict(exclude=exclude, exclude_none=exclude_none)
                            continue
                        # Check if the value is JSON serializable
                        if isinstance(v, (str, int, float, bool, type(None), list, dict)):
                            serialized_dict[k] = v
                            continue
                        logger.debug(
                            f"Skipping non-serializable value for key '{k}' in dict attribute '{key}' "
                            f"of type {type(v).__name__}"
                        )
                    result[key] = serialized_dict
                else:
                    result[key] = value

        return result

    def to_json(self, *, exclude: set[str] | None = None, exclude_none: bool = True) -> str:
        """Convert the instance to a JSON string.

        Args:
            exclude: Set of field names to exclude from serialization.
            exclude_none: Whether to exclude None values from the output. Defaults to True.

        Returns:
            JSON string representation of the instance.
        """
        return json.dumps(self.to_dict(exclude=exclude, exclude_none=exclude_none))

    @classmethod
    def from_dict(
        cls: type[TClass], value: MutableMapping[str, Any], /, dependencies: MutableMapping[str, Any] | None = None
    ) -> TClass:
        """Create an instance from a dictionary.

        Args:
            value: Dictionary containing the instance data (positional-only).
            dependencies: Dictionary mapping dependency keys to values.
                Keys should be in format "<type>.<parameter>" or "<type>.<dict-parameter>.<key>".

        Returns:
            New instance of the class.
        """
        if dependencies is None:
            dependencies = {}

        # Get the type identifier
        type_id = cls._get_type_identifier()

        # Create a copy of the value dict to work with, filtering out the 'type' key
        kwargs = {k: v for k, v in value.items() if k != "type"}

        # Process dependencies
        for dep_key, dep_value in dependencies.items():
            parts = dep_key.split(".")
            if len(parts) < 2:
                continue

            dep_type = parts[0]
            if dep_type != type_id:
                continue

            param_name = parts[1]

            # Log debug message if dependency is not in INJECTABLE
            if param_name not in cls.INJECTABLE:
                logger.debug(
                    f"Dependency '{param_name}' for type '{type_id}' is not in INJECTABLE set. "
                    f"Available injectable parameters: {cls.INJECTABLE}"
                )

            if len(parts) == 2:
                # Simple parameter: <type>.<parameter>
                kwargs[param_name] = dep_value
            elif len(parts) == 3:
                # Dict parameter: <type>.<dict-parameter>.<key>
                dict_param_name = parts[1]
                key = parts[2]
                if dict_param_name not in kwargs:
                    kwargs[dict_param_name] = {}
                kwargs[dict_param_name][key] = dep_value

        return cls(**kwargs)

    @classmethod
    def from_json(cls: type[TClass], value: str, /, dependencies: MutableMapping[str, Any] | None = None) -> TClass:
        """Create an instance from a JSON string.

        Args:
            value: JSON string containing the instance data (positional-only).
            dependencies: Dictionary mapping dependency keys to values.
                Keys should be in format "<type>.<parameter>" or "<type>.<dict-parameter>.<key>".

        Returns:
            New instance of the class.
        """
        data = json.loads(value)
        return cls.from_dict(data, dependencies=dependencies)

    @classmethod
    def _get_type_identifier(cls) -> str:
        """Get the type identifier for this class.

        Returns the value of the 'type' class variable if present,
        otherwise returns a snake_cased version of the class name.

        Returns:
            Type identifier string.
        """
        if (type_ := getattr(cls, "type", None)) and isinstance(type_, str):
            return type_

        # Convert class name to snake_case
        return _CAMEL_TO_SNAKE_PATTERN.sub("_", cls.__name__).lower()
