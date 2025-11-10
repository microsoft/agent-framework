# Copyright (c) Microsoft. All rights reserved.

from dataclasses import dataclass
from typing import Any, Generic, TypeVar, Union

from agent_framework import RequestInfoEvent
from agent_framework._workflows._typing_utils import (
    deserialize_type,
    is_instance_of,
    is_type_compatible,
    serialize_type,
)


def test_basic_types() -> None:
    """Test basic built-in types."""
    assert is_instance_of(5, int)
    assert is_instance_of("hello", str)
    assert is_instance_of(None, type(None))


def test_union_types() -> None:
    """Test union types (|) and optional types."""
    assert is_instance_of(5, int | str)
    assert is_instance_of("hello", int | str)
    assert is_instance_of(5, Union[int, str])
    assert not is_instance_of(5.0, int | str)


def test_list_types() -> None:
    """Test list types with various element types."""
    assert is_instance_of([], list)
    assert is_instance_of([1, 2, 3], list)
    assert is_instance_of([1, 2, 3], list[int])
    assert is_instance_of([1, 2, 3], list[int | str])
    assert is_instance_of([1, "a", 3], list[int | str])
    assert is_instance_of([1, "a", 3], list[Union[int, str]])
    assert not is_instance_of([1, 2.0, 3], dict)
    assert not is_instance_of([1, 2.0, 3], list[int | str])


def test_tuple_types() -> None:
    """Test tuple types with fixed and variable lengths."""
    assert is_instance_of((1, "a"), tuple)
    assert is_instance_of((1, "a"), tuple[int, str])
    assert is_instance_of((1, "a", 3), tuple[int | str, ...])
    assert is_instance_of((1, 2.0, "a"), tuple[...])  # type: ignore
    assert not is_instance_of((1, 2.0, 3), tuple[int | str, ...])
    assert not is_instance_of((1, 2.0, 3), dict)


def test_dict_types() -> None:
    """Test dictionary types with typed keys and values."""
    assert is_instance_of({"key": "value"}, dict)
    assert is_instance_of({"key": "value"}, dict[str, str])
    assert is_instance_of({"key": 5, "another_key": "value"}, dict[str, int | str])
    assert not is_instance_of({"key": 5, "another_key": 3.0}, dict[str, int | str])
    assert not is_instance_of({"key": 5, "another_key": 3.0}, list)


def test_set_types() -> None:
    """Test set types with various element types."""
    assert is_instance_of({1, 2, 3}, set)
    assert is_instance_of({1, 2, 3}, set[int])
    assert is_instance_of({1, 2, 3}, set[int | str])
    assert is_instance_of({1, "a", 3}, set[int | str])
    assert is_instance_of({1, "a", 3}, set[Union[int, str]])
    assert is_instance_of(set(), set[int])
    assert not is_instance_of({1, 2.0, 3}, set[int | str])
    assert not is_instance_of({1, 2, 3}, list)
    assert not is_instance_of({1, 2, 3}, dict)


def test_any_type() -> None:
    """Test Any type - should accept all values."""
    assert is_instance_of(5, Any)
    assert is_instance_of("hello", Any)
    assert is_instance_of([1, 2, 3], Any)


def test_nested_types() -> None:
    """Test complex nested type structures."""
    assert is_instance_of([{"key": [1, 2]}, {"another_key": [3]}], list[dict[str, list[int]]])
    assert not is_instance_of([{"key": [1, 2]}, {"another_key": [3.0]}], list[dict[str, list[int]]])


def test_custom_type() -> None:
    """Test custom object type checking."""

    @dataclass
    class CustomClass:
        value: int

    instance = CustomClass(10)
    assert is_instance_of(instance, CustomClass)
    assert not is_instance_of(instance, dict)


def test_custom_generic_type() -> None:
    """Test custom generic type checking."""

    T = TypeVar("T")
    U = TypeVar("U")

    class CustomClass(Generic[T, U]):
        def __init__(self, request: T, response: U, extra: Any | None = None) -> None:
            self.request = request
            self.response = response
            self.extra = extra

    instance = CustomClass[int, str](request=5, response="response")

    assert is_instance_of(instance, CustomClass[int, str])
    # Generic parameters are not strictly enforced at runtime
    assert is_instance_of(instance, CustomClass[str, str])


def test_edge_cases() -> None:
    """Test edge cases and unusual scenarios."""
    assert is_instance_of([], list[int])  # Empty list should be valid
    assert is_instance_of((), tuple[int, ...])  # Empty tuple should be valid
    assert is_instance_of({}, dict[str, int])  # Empty dict should be valid
    assert is_instance_of(None, int | None)  # Optional type with None
    assert not is_instance_of(5, str | None)  # Optional type without matching type


def test_serialize_type() -> None:
    """Test serialization of types to strings."""
    # Test built-in types
    assert serialize_type(int) == "builtins.int"
    assert serialize_type(str) == "builtins.str"
    assert serialize_type(float) == "builtins.float"
    assert serialize_type(bool) == "builtins.bool"
    assert serialize_type(list) == "builtins.list"
    assert serialize_type(dict) == "builtins.dict"
    assert serialize_type(tuple) == "builtins.tuple"
    assert serialize_type(set) == "builtins.set"

    # Test custom class
    @dataclass
    class TestClass:
        value: int

    # The custom class will be in the test module
    expected = f"{TestClass.__module__}.{TestClass.__qualname__}"
    assert serialize_type(TestClass) == expected


def test_deserialize_type() -> None:
    """Test deserialization of type strings back to types."""
    # Test built-in types
    assert deserialize_type("builtins.int") is int
    assert deserialize_type("builtins.str") is str
    assert deserialize_type("builtins.float") is float
    assert deserialize_type("builtins.bool") is bool
    assert deserialize_type("builtins.list") is list
    assert deserialize_type("builtins.dict") is dict
    assert deserialize_type("builtins.tuple") is tuple
    assert deserialize_type("builtins.set") is set


def test_serialize_deserialize_roundtrip() -> None:
    """Test that serialization and deserialization are inverse operations."""
    # Test built-in types
    types_to_test = [int, str, float, bool, list, dict, tuple, set]

    for type_to_test in types_to_test:
        serialized = serialize_type(type_to_test)
        deserialized = deserialize_type(serialized)
        assert deserialized is type_to_test

    # Test agent framework type roundtrip

    serialized = serialize_type(RequestInfoEvent)
    deserialized = deserialize_type(serialized)
    assert deserialized is RequestInfoEvent

    # Verify we can instantiate the deserialized type
    instance = deserialized(
        request_id="request-123",
        source_executor_id="executor_1",
        request_data="test",
        response_type=str,
    )
    assert isinstance(instance, RequestInfoEvent)


def test_deserialize_type_error_handling() -> None:
    """Test error handling in deserialize_type function."""
    import pytest

    # Test with non-existent module
    with pytest.raises(ModuleNotFoundError):
        deserialize_type("nonexistent.module.Type")

    # Test with non-existent type in existing module
    with pytest.raises(AttributeError):
        deserialize_type("builtins.NonExistentType")


def test_type_compatibility_basic() -> None:
    """Test basic type compatibility scenarios."""
    # Exact type match
    assert is_type_compatible(str, str)
    assert is_type_compatible(int, int)

    # bool is a subtype of int
    assert is_type_compatible(bool, int)

    # Any compatibility
    assert is_type_compatible(str, Any)
    assert is_type_compatible(list[int], Any)

    # Subclass compatibility
    class Animal:
        pass

    class Dog(Animal):
        pass

    assert is_type_compatible(Dog, Animal)
    assert not is_type_compatible(Animal, Dog)


def test_type_compatibility_unions() -> None:
    """Test type compatibility with Union types."""
    # Source matches target union member
    assert is_type_compatible(str, Union[str, int])
    assert is_type_compatible(int, Union[str, int])
    assert not is_type_compatible(float, Union[str, int])

    # Source union - all members must be compatible with target
    assert is_type_compatible(Union[str, int], Union[str, int, float])
    assert not is_type_compatible(Union[str, int, bytes], Union[str, int])


def test_type_compatibility_collections() -> None:
    """Test type compatibility with collection types."""

    # List compatibility - key use case
    @dataclass
    class ChatMessage:
        text: str

    assert is_type_compatible(list[ChatMessage], list[Union[str, ChatMessage]])
    assert is_type_compatible(list[str], list[Union[str, ChatMessage]])
    assert not is_type_compatible(list[Union[str, ChatMessage]], list[ChatMessage])

    # Dict compatibility
    assert is_type_compatible(dict[str, int], dict[str, Union[int, float]])
    assert not is_type_compatible(dict[str, Union[int, float]], dict[str, int])

    # Set compatibility
    assert is_type_compatible(set[str], set[Union[str, int]])
    assert not is_type_compatible(set[Union[str, int]], set[str])


def test_type_compatibility_tuples() -> None:
    """Test type compatibility with tuple types."""
    # Fixed length tuples
    assert is_type_compatible(tuple[str, int], tuple[Union[str, bytes], Union[int, float]])
    assert not is_type_compatible(tuple[str, int], tuple[str, int, bool])  # Different lengths

    # Variable length tuples
    assert is_type_compatible(tuple[str, ...], tuple[Union[str, bytes], ...])
    assert is_type_compatible(tuple[str, int, bool], tuple[Union[str, int, bool], ...])
    assert not is_type_compatible(tuple[str, ...], tuple[str, int])  # Variable to fixed


def test_type_compatibility_complex() -> None:
    """Test complex nested type compatibility."""

    @dataclass
    class Message:
        content: str

    # Complex nested structure
    source = list[dict[str, Message]]
    target = list[dict[Union[str, bytes], Union[str, Message]]]
    assert is_type_compatible(source, target)

    # Incompatible nested structure
    incompatible_target = list[dict[Union[str, bytes], int]]
    assert not is_type_compatible(source, incompatible_target)
