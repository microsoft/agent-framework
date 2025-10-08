# Copyright (c) Microsoft. All rights reserved.

import json
import re
from collections.abc import Mapping, MutableMapping
from typing import Any, ClassVar, Protocol, TypeVar, runtime_checkable

from ._logging import get_logger

logger = get_logger()

TClass = TypeVar("TClass", bound="SerializationMixin")
TProtocol = TypeVar("TProtocol", bound="SerializationProtocol")

# Regex pattern for converting CamelCase to snake_case
_CAMEL_TO_SNAKE_PATTERN = re.compile(r"(?<!^)(?=[A-Z])")


@runtime_checkable
class SerializationProtocol(Protocol):
    """Protocol for objects that support serialization and deserialization.

    This protocol defines the interface for objects that can be converted to and from dictionaries.

    Examples:
        .. code-block:: python

            from agent_framework import SerializationProtocol


            class MySerializable:
                def __init__(self, value: str):
                    self.value = value

                def to_dict(self, **kwargs):
                    return {"value": self.value}

                @classmethod
                def from_dict(cls, value, **kwargs):
                    return cls(value["value"])


            # Verify it implements the protocol
            assert isinstance(MySerializable("test"), SerializationProtocol)
    """

    def to_dict(self, **kwargs: Any) -> dict[str, Any]:
        """Convert the instance to a dictionary.

        Keyword Args:
            kwargs: Additional keyword arguments for serialization.

        Returns:
            Dictionary representation of the instance.
        """
        ...

    @classmethod
    def from_dict(cls: type[TProtocol], value: MutableMapping[str, Any], /, **kwargs: Any) -> TProtocol:
        """Create an instance from a dictionary.

        Args:
            value: Dictionary containing the instance data (positional-only).

        Keyword Args:
            kwargs: Additional keyword arguments for deserialization.

        Returns:
            New instance of the class.
        """
        ...


def is_serializable(value: Any) -> bool:
    """Check if a value is JSON serializable.

    Args:
        value: The value to check.

    Returns:
        True if the value is JSON serializable, False otherwise.
    """
    return isinstance(value, (str, int, float, bool, type(None), list, dict))


class SerializationMixin:
    """Mixin class providing serialization and deserialization capabilities.

    Classes using this mixin should handle MutableMapping inputs in their __init__ method
    for any parameters that expect SerializationMixin/SerializationProtocol instances.
    The __init__ should check if the value is a MutableMapping and call from_dict() to convert it.

    So take the two classes below as an example. The first purely uses base types, strings in this case.
    The second has a param that is of the type of the first class.
    Because we setup the __init__ method to handle MutableMapping,
    we can pass in a dict to the second class and it will convert it to an instance of the first class.

    Examples:
        .. code-block:: python

            class SerializableMixinType(SerializationMixin):
                def __init__(self, param1: str, param2: int) -> None:
                    self.param1 = param1
                    self.param2 = param2


            class MyClass(SerializationMixin):
                def __init__(
                    self,
                    regular_param: str,
                    param: SerializableMixinType | MutableMapping[str, Any] | None = None,
                ) -> None:
                    if isinstance(param, MutableMapping):
                        self.param = self.from_dict(param)
                    else:
                        self.param = param
                    self.regular_param = regular_param


            instance = MyClass.from_dict({"regular_param": "value", "param": {"param1": "value1", "param2": 42}})

    A more complex use case involves an injectable dependency that is not serialized.
    In this case, the dependency is passed in via the dependencies parameter to from_dict/from_json.

    Examples:
        .. code-block:: python

            from library import Client


            class MyClass(SerializationMixin):
                INJECTABLE = {"client"}

    During serialization, the field listed as INJECTABLE (and also DEFAULT_EXCLUDE) will be excluded from the output.
    Then in deserialization, the dependencies dict uses a nested structure:
    ``{"<type>": {"<parameter>": value}}`` where ``<type>`` is the type identifier for the class
    (either the value of the 'type' class variable or the snake_cased class name if 'type' is not present),
    and ``<parameter>`` is the name of the injectable parameter in the __init__ method.
    For dict parameters, the structure is ``{"<type>": {"<dict-parameter>": {"<key>": value}}}``.
    For instance-specific dependencies, use ``{"<type>": {"<field>:<name>": {"<parameter>": value}}}``.
    """

    DEFAULT_EXCLUDE: ClassVar[set[str]] = set()
    INJECTABLE: ClassVar[set[str]] = set()

    def to_dict(self, *, exclude: set[str] | None = None, exclude_none: bool = True) -> dict[str, Any]:
        """Convert the instance and any nested objects to a dictionary.

        Keyword Args:
            exclude: The set of field names to exclude from serialization.
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
        result: dict[str, Any] = {} if "type" in combined_exclude else {"type": self._get_type_identifier()}
        for key, value in self.__dict__.items():
            if key not in combined_exclude and not key.startswith("_"):
                if exclude_none and value is None:
                    continue
                # Recursively serialize SerializationProtocol objects
                if isinstance(value, SerializationProtocol):
                    result[key] = value.to_dict(exclude=exclude, exclude_none=exclude_none)
                    continue
                # Handle lists containing SerializationProtocol objects
                if isinstance(value, list):
                    value_as_list: list[Any] = []
                    for item in value:
                        if isinstance(item, SerializationProtocol):
                            value_as_list.append(item.to_dict(exclude=exclude, exclude_none=exclude_none))
                            continue
                        if is_serializable(item):
                            value_as_list.append(item)
                            continue
                        logger.debug(
                            f"Skipping non-serializable item in list attribute '{key}' of type {type(item).__name__}"
                        )
                    result[key] = value_as_list
                    continue
                # Handle dicts containing SerializationProtocol values
                if isinstance(value, dict):
                    serialized_dict: dict[str, Any] = {}
                    for k, v in value.items():
                        if isinstance(v, SerializationProtocol):
                            serialized_dict[k] = v.to_dict(exclude=exclude, exclude_none=exclude_none)
                            continue
                        # Check if the value is JSON serializable
                        if is_serializable(v):
                            serialized_dict[k] = v
                            continue
                        logger.debug(
                            f"Skipping non-serializable value for key '{k}' in dict attribute '{key}' "
                            f"of type {type(v).__name__}"
                        )
                    result[key] = serialized_dict
                    continue
                # Directly include JSON serializable values
                if is_serializable(value):
                    result[key] = value
                    continue
                logger.debug(f"Skipping non-serializable attribute '{key}' of type {type(value).__name__}")

        return result

    def to_json(self, *, exclude: set[str] | None = None, exclude_none: bool = True, **kwargs: Any) -> str:
        """Convert the instance to a JSON string.

        Keyword Args:
            exclude: The set of field names to exclude from serialization.
            exclude_none: Whether to exclude None values from the output. Defaults to True.
            **kwargs: passed through to the json.dumps method.

        Returns:
            JSON string representation of the instance.
        """
        return json.dumps(self.to_dict(exclude=exclude, exclude_none=exclude_none), **kwargs)

    @classmethod
    def from_dict(
        cls: type[TClass], value: MutableMapping[str, Any], /, *, dependencies: MutableMapping[str, Any] | None = None
    ) -> TClass:
        """Create an instance from a dictionary.

        Args:
            value: The dictionary containing the instance data (positional-only).

        Keyword Args:
            dependencies: A nested dictionary mapping type identifiers to their injectable dependencies.
                Structure: ``{"<type>": {"<parameter>": value, ...}}`` for simple parameters,
                ``{"<type>": {"<dict-parameter>": {"<key>": value}}}`` for dict parameters,
                or ``{"<type>": {"<instance-key>": {"<parameter>": value}}}`` for instance-specific dependencies.

        Returns:
            New instance of the class.

        Examples:
            Simple parameter injection:

            .. code-block:: python

                class MyClass(SerializationMixin):
                    INJECTABLE = {"client"}

                    def __init__(self, value: str, client=None):
                        self.value = value
                        self.client = client


                data = {"type": "my_class", "value": "test"}
                dependencies = {"my_class": {"client": client_instance}}
                obj = MyClass.from_dict(data, dependencies=dependencies)

            Dict parameter injection:

            .. code-block:: python

                class ConfigClass(SerializationMixin):
                    INJECTABLE = {"config"}

                    def __init__(self, name: str, config: dict | None = None):
                        self.name = name
                        self.config = config or {}


                data = {"type": "config_class", "name": "app"}
                dependencies = {"config_class": {"config": {"api_key": "secret", "timeout": 30}}}
                obj = ConfigClass.from_dict(data, dependencies=dependencies)

            Instance-specific injection (when multiple instances of same type need different dependencies):

            .. code-block:: python

                class Worker(SerializationMixin):
                    INJECTABLE = {"func"}

                    def __init__(self, name: str, func=None):
                        self.name = name
                        self.func = func


                data = {"type": "worker", "name": "worker1"}
                dependencies = {"worker": {"name:worker1": {"func": my_function}}}
                obj = Worker.from_dict(data, dependencies=dependencies)
        """
        if dependencies is None:
            dependencies = {}

        # Get the type identifier
        type_id = cls._get_type_identifier(value)

        if (supplied_type := value.get("type")) and supplied_type != type_id:
            raise ValueError(f"Type mismatch: expected '{type_id}', got '{supplied_type}'")

        # Create a copy of the value dict to work with, filtering out the 'type' key
        kwargs = {k: v for k, v in value.items() if k != "type"}

        # Process dependencies using dict-based structure
        type_deps = dependencies.get(type_id, {})
        for dep_key, dep_value in type_deps.items():
            # Check if this is an instance-specific dependency (field:name format)
            if ":" in dep_key:
                field, name = dep_key.split(":", 1)
                # Only apply if the instance matches
                if kwargs.get(field) == name and isinstance(dep_value, dict):
                    # Apply instance-specific dependencies
                    for param_name, param_value in dep_value.items():
                        if param_name not in cls.INJECTABLE:
                            logger.debug(
                                f"Dependency '{param_name}' for type '{type_id}' is not in INJECTABLE set. "
                                f"Available injectable parameters: {cls.INJECTABLE}"
                            )
                        # Handle nested dict parameters
                        if (
                            isinstance(param_value, dict)
                            and param_name in kwargs
                            and isinstance(kwargs[param_name], dict)
                        ):
                            kwargs[param_name].update(param_value)
                        else:
                            kwargs[param_name] = param_value
            else:
                # Regular parameter dependency
                if dep_key not in cls.INJECTABLE:
                    logger.debug(
                        f"Dependency '{dep_key}' for type '{type_id}' is not in INJECTABLE set. "
                        f"Available injectable parameters: {cls.INJECTABLE}"
                    )
                # Handle dict parameters - merge if both are dicts
                if isinstance(dep_value, dict) and dep_key in kwargs and isinstance(kwargs[dep_key], dict):
                    kwargs[dep_key].update(dep_value)
                else:
                    kwargs[dep_key] = dep_value

        return cls(**kwargs)

    @classmethod
    def from_json(cls: type[TClass], value: str, /, *, dependencies: MutableMapping[str, Any] | None = None) -> TClass:
        """Create an instance from a JSON string.

        Args:
            value: The JSON string containing the instance data (positional-only).

        Keyword Args:
            dependencies: A nested dictionary mapping type identifiers to their injectable dependencies.
                See :meth:`from_dict` for structure and examples.

        Returns:
            New instance of the class.
        """
        data = json.loads(value)
        return cls.from_dict(data, dependencies=dependencies)

    @classmethod
    def _get_type_identifier(cls, value: Mapping[str, Any] | None = None) -> str:
        """Get the type identifier for this class.

        Returns the value of the ``type`` class variable if present,
        otherwise returns a snake_cased version of the class name.

        Returns:
            Type identifier string.
        """
        # for from_dict
        if value and (type_ := value.get("type")) and isinstance(type_, str):
            return type_  # type:ignore[no-any-return]
        # for todict when defined per instance
        if (type_ := getattr(cls, "type", None)) and isinstance(type_, str):
            return type_  # type:ignore[no-any-return]
        # for both when defined on class.
        if (type_ := getattr(cls, "TYPE", None)) and isinstance(type_, str):
            return type_  # type:ignore[no-any-return]
        # fallback and default
        # Convert class name to snake_case
        return _CAMEL_TO_SNAKE_PATTERN.sub("_", cls.__name__).lower()
