# Copyright (c) Microsoft. All rights reserved.

from dataclasses import dataclass
from typing import Any, Generic, Optional, TypeVar, Union

import pytest

from agent_framework import WorkflowEvent
from agent_framework._workflows._typing_utils import (
    deserialize_type,
    is_instance_of,
    is_type_compatible,
    normalize_type_to_list,
    resolve_type_annotation,
    serialize_type,
    try_coerce_to_type,
)

# region: normalize_type_to_list tests


def test_normalize_type_to_list_single_type() -> None:
    """Test normalize_type_to_list with single types."""
    assert normalize_type_to_list(str) == [str]
    assert normalize_type_to_list(int) == [int]
    assert normalize_type_to_list(float) == [float]
    assert normalize_type_to_list(bool) == [bool]
    assert normalize_type_to_list(list) == [list]
    assert normalize_type_to_list(dict) == [dict]


def test_normalize_type_to_list_none() -> None:
    """Test normalize_type_to_list with None returns empty list."""
    assert normalize_type_to_list(None) == []


def test_normalize_type_to_list_union_pipe_syntax() -> None:
    """Test normalize_type_to_list with union types using | syntax."""
    result = normalize_type_to_list(str | int)
    assert set(result) == {str, int}

    result = normalize_type_to_list(str | int | bool)
    assert set(result) == {str, int, bool}


def test_normalize_type_to_list_union_typing_syntax() -> None:
    """Test normalize_type_to_list with Union[] from typing module."""
    result = normalize_type_to_list(Union[str, int])
    assert set(result) == {str, int}

    result = normalize_type_to_list(Union[str, int, bool])
    assert set(result) == {str, int, bool}


def test_normalize_type_to_list_optional() -> None:
    """Test normalize_type_to_list with Optional types (Union[T, None])."""
    # Optional[str] is Union[str, None]
    result = normalize_type_to_list(Optional[str])
    assert str in result
    assert type(None) in result
    assert len(result) == 2

    # str | None is equivalent
    result = normalize_type_to_list(str | None)
    assert str in result
    assert type(None) in result
    assert len(result) == 2


def test_normalize_type_to_list_custom_types() -> None:
    """Test normalize_type_to_list with custom class types."""

    @dataclass
    class CustomMessage:
        content: str

    result = normalize_type_to_list(CustomMessage)
    assert result == [CustomMessage]

    result = normalize_type_to_list(CustomMessage | str)
    assert set(result) == {CustomMessage, str}


# endregion: normalize_type_to_list tests


# region: resolve_type_annotation tests


def test_resolve_type_annotation_none() -> None:
    """Test resolve_type_annotation with None returns None."""
    assert resolve_type_annotation(None) is None


def test_resolve_type_annotation_actual_types() -> None:
    """Test resolve_type_annotation passes through actual types unchanged."""
    assert resolve_type_annotation(str) is str
    assert resolve_type_annotation(int) is int
    assert resolve_type_annotation(str | int) == str | int


def test_resolve_type_annotation_string_builtin() -> None:
    """Test resolve_type_annotation resolves string references to builtin types."""
    result = resolve_type_annotation("str", {"str": str})
    assert result is str

    result = resolve_type_annotation("int", {"int": int})
    assert result is int


def test_resolve_type_annotation_string_union() -> None:
    """Test resolve_type_annotation resolves string union types."""
    result = resolve_type_annotation("str | int", {"str": str, "int": int})
    assert result == str | int


def test_resolve_type_annotation_string_custom_type() -> None:
    """Test resolve_type_annotation resolves string references to custom types."""

    @dataclass
    class MyCustomType:
        value: int

    result = resolve_type_annotation("MyCustomType", {"MyCustomType": MyCustomType})
    assert result is MyCustomType

    result = resolve_type_annotation("MyCustomType | str", {"MyCustomType": MyCustomType, "str": str})
    assert set(result.__args__) == {MyCustomType, str}  # type: ignore[union-attr]


def test_resolve_type_annotation_string_typing_union() -> None:
    """Test resolve_type_annotation resolves Union[] syntax in strings."""
    result = resolve_type_annotation("Union[str, int]", {"str": str, "int": int})
    assert set(result.__args__) == {str, int}  # type: ignore[union-attr]


def test_resolve_type_annotation_string_optional() -> None:
    """Test resolve_type_annotation resolves Optional[] syntax in strings."""
    result = resolve_type_annotation("Optional[str]", {"str": str})
    assert str in result.__args__  # type: ignore[union-attr]
    assert type(None) in result.__args__  # type: ignore[union-attr]


def test_resolve_type_annotation_unresolvable_raises() -> None:
    """Test resolve_type_annotation raises NameError for unresolvable types."""
    with pytest.raises(NameError, match="Could not resolve type annotation"):
        resolve_type_annotation("NonExistentType", {})


# endregion: resolve_type_annotation tests


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

    serialized = serialize_type(WorkflowEvent)
    deserialized = deserialize_type(serialized)
    assert deserialized is WorkflowEvent

    # Verify we can instantiate the deserialized type via factory method
    instance = WorkflowEvent.request_info(
        request_id="request-123",
        source_executor_id="executor_1",
        request_data="test",
        response_type=str,
    )
    assert isinstance(instance, WorkflowEvent)
    assert instance.type == "request_info"


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
    class Message:
        text: str

    assert is_type_compatible(list[Message], list[Union[str, Message]])
    assert is_type_compatible(list[str], list[Union[str, Message]])
    assert not is_type_compatible(list[Union[str, Message]], list[Message])

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


# region: try_coerce_to_type tests


def test_coerce_already_correct_type() -> None:
    """Values already matching the target type are returned as-is."""
    assert try_coerce_to_type(42, int) == 42
    assert try_coerce_to_type("hello", str) == "hello"
    assert try_coerce_to_type(True, bool) is True


def test_coerce_int_to_float() -> None:
    """JSON integers should be coercible to float."""
    result = try_coerce_to_type(1, float)
    assert result == 1.0
    assert isinstance(result, float)


def test_coerce_dict_to_dataclass() -> None:
    """Dicts (from JSON) should be coercible to dataclasses."""

    @dataclass
    class Point:
        x: int
        y: int

    result = try_coerce_to_type({"x": 1, "y": 2}, Point)
    assert isinstance(result, Point)
    assert result.x == 1
    assert result.y == 2


def test_coerce_dict_to_dataclass_bad_keys_returns_original() -> None:
    """Dicts with wrong keys should return the original dict, not raise."""

    @dataclass
    class Point:
        x: int
        y: int

    original = {"a": 1, "b": 2}
    result = try_coerce_to_type(original, Point)
    assert result is original


def test_coerce_non_concrete_target_returns_original() -> None:
    """Union and other non-concrete types should return the original value."""
    result = try_coerce_to_type(42, int | str)
    assert result == 42

    result = try_coerce_to_type({"x": 1}, Union[str, int])
    assert result == {"x": 1}


def test_coerce_unrelated_types_returns_original() -> None:
    """Coercion between unrelated types should return the original value."""
    assert try_coerce_to_type("hello", int) == "hello"
    assert try_coerce_to_type(3.14, str) == 3.14
    assert try_coerce_to_type([1, 2], dict) == [1, 2]


def test_coerce_any_returns_original() -> None:
    """Any target type should accept any value without coercion."""
    assert try_coerce_to_type(42, Any) == 42
    assert try_coerce_to_type({"k": "v"}, Any) == {"k": "v"}


# endregion: try_coerce_to_type tests
