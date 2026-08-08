# Copyright (c) Microsoft. All rights reserved.

import importlib
import sys
import typing
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Generic, Optional, TypeVar, Union

import pytest

from agent_framework import Message, WorkflowEvent
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
    result = normalize_type_to_list(str | int)  # pyright: ignore[reportArgumentType]
    assert set(result) == {str, int}

    result = normalize_type_to_list(str | int | bool)  # pyright: ignore[reportArgumentType]
    assert set(result) == {str, int, bool}


def test_normalize_type_to_list_union_typing_syntax() -> None:
    """Test normalize_type_to_list with Union[] from typing module."""
    result = normalize_type_to_list(Union[str, int])  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
    assert set(result) == {str, int}

    result = normalize_type_to_list(Union[str, int, bool])  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
    assert set(result) == {str, int, bool}


def test_normalize_type_to_list_optional() -> None:
    """Test normalize_type_to_list with Optional types (Union[T, None])."""
    # Optional[str] is Union[str, None]
    result = normalize_type_to_list(Optional[str])  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
    assert str in result
    assert type(None) in result
    assert len(result) == 2

    # str | None is equivalent
    result = normalize_type_to_list(str | None)  # pyright: ignore[reportArgumentType]
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

    result = normalize_type_to_list(CustomMessage | str)  # pyright: ignore[reportArgumentType]
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
    assert resolve_type_annotation(str | int) == str | int  # pyright: ignore[reportArgumentType]


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
    assert set(result.__args__) == {MyCustomType, str}  # type: ignore[union-attr]  # ty: ignore[unresolved-attribute]


def test_resolve_type_annotation_string_typing_union() -> None:
    """Test resolve_type_annotation resolves Union[] syntax in strings."""
    result = resolve_type_annotation("Union[str, int]", {"str": str, "int": int})
    assert set(result.__args__) == {str, int}  # type: ignore[union-attr]  # ty: ignore[unresolved-attribute]


def test_resolve_type_annotation_string_optional() -> None:
    """Test resolve_type_annotation resolves Optional[] syntax in strings."""
    result = resolve_type_annotation("Optional[str]", {"str": str})
    assert str in result.__args__  # type: ignore[union-attr]  # ty: ignore[unresolved-attribute]
    assert type(None) in result.__args__  # type: ignore[union-attr]  # ty: ignore[unresolved-attribute]


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


def test_serialize_type_parameterized_generic_preserves_wire_name() -> None:
    """Parameterized generics preserve their historical wire names."""
    serialized_name = serialize_type(list[Message])

    assert serialized_name == "builtins.list"
    assert deserialize_type(serialized_name) is list
    legacy_list_alias = vars(typing)["List"]
    legacy_list = legacy_list_alias[Message]
    legacy_serialized_name = serialize_type(legacy_list)
    assert legacy_serialized_name == "typing.List"
    assert deserialize_type(legacy_serialized_name) is legacy_list_alias


@pytest.mark.parametrize(
    "alias_name",
    ["List", "Dict", "Tuple", "Set", "FrozenSet", "Sequence", "Mapping", "Callable", "Type"],
)
def test_deserialize_type_supports_legacy_typing_aliases(alias_name: str) -> None:
    """Trusted standard typing aliases retain their historical wire compatibility."""
    legacy_alias = vars(typing)[alias_name]
    serialized_name = f"typing.{alias_name}"

    assert serialize_type(legacy_alias) == serialized_name
    assert deserialize_type(serialized_name) is legacy_alias


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


def test_deserialize_type_accepts_explicit_custom_type_mapping() -> None:
    """Callers can resolve a trusted custom type without first serializing it."""

    class ExplicitlyAllowedType:
        pass

    serialized_name = f"{ExplicitlyAllowedType.__module__}.{ExplicitlyAllowedType.__qualname__}"

    assert (
        deserialize_type(serialized_name, allowed_types={serialized_name: ExplicitlyAllowedType})
        is ExplicitlyAllowedType
    )


def test_deserialize_type_accepts_historical_optional_name_for_union_annotation() -> None:
    """A trusted Optional annotation can rehydrate payloads emitted before runtime canonicalization."""
    optional_string = str | None

    assert deserialize_type("typing.Optional", allowed_types={"typing.Optional": optional_string}) == optional_string


def test_serialize_type_preserves_unusual_runtime_type_name() -> None:
    """Compatibility names remain the exact module and qualified name strings."""

    class UnusualType:
        pass

    UnusualType.__qualname__ = "Request-Type"
    expected_name = f"{UnusualType.__module__}.{UnusualType.__qualname__}"

    assert serialize_type(UnusualType) == expected_name
    assert deserialize_type(expected_name, allowed_types={expected_name: UnusualType}) is UnusualType


def test_deserialize_type_rejects_non_type_mapping_value() -> None:
    """Explicit compatibility mappings cannot resolve arbitrary objects."""
    invalid_mapping: Any = {"trusted.Request": object()}

    with pytest.raises(TypeError, match="must be an actual type"):
        deserialize_type("trusted.Request", allowed_types=invalid_mapping)


def test_deserialize_type_rejects_alias_mapping() -> None:
    """A type cannot be authorized under a different serialized name."""

    class TrustedRequest:
        pass

    with pytest.raises(ValueError, match="does not match the supplied type"):
        deserialize_type("trusted.Alias", allowed_types={"trusted.Alias": TrustedRequest})


def test_deserialize_type_rejects_subclass_for_base_name() -> None:
    """Subclass compatibility is insufficient for serialized type identity."""

    class BaseRequest:
        pass

    class DerivedRequest(BaseRequest):
        pass

    base_name = f"{BaseRequest.__module__}.{BaseRequest.__qualname__}"
    with pytest.raises(ValueError, match="does not match the supplied type"):
        deserialize_type(base_name, allowed_types={base_name: DerivedRequest})


def test_deserialize_type_explicit_mapping_resolves_same_named_local_type() -> None:
    """An exact per-call mapping selects a trusted local type with a reused compatibility name."""

    class RegisteredRequest:
        pass

    class ConflictingRequest:
        pass

    serialized_name = serialize_type(RegisteredRequest)
    ConflictingRequest.__module__ = RegisteredRequest.__module__
    ConflictingRequest.__qualname__ = RegisteredRequest.__qualname__

    assert deserialize_type(serialized_name, allowed_types={serialized_name: ConflictingRequest}) is ConflictingRequest


def test_serialize_type_allows_repeated_factory_types_with_same_name() -> None:
    """Independent factories can serialize distinct types that share one compatibility name."""

    def make_request_type() -> type:
        class Request:
            pass

        return Request

    first_type = make_request_type()
    second_type = make_request_type()

    serialized_name = serialize_type(first_type)
    assert serialize_type(second_type) == serialized_name

    with pytest.raises(ModuleNotFoundError, match="<locals>"):
        deserialize_type(serialized_name)

    assert deserialize_type(serialized_name, allowed_types={serialized_name: second_type}) is second_type


def test_serialize_type_allows_reloaded_type_with_same_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Module reload can replace a type without permanently poisoning serialization."""
    module_name = "_request_info_reload_type"
    module_path = tmp_path / f"{module_name}.py"
    module_path.write_text("class ReloadedRequest:\n    pass\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()

    module = importlib.import_module(module_name)
    try:
        first_type = module.ReloadedRequest
        serialized_name = serialize_type(first_type)

        reloaded_module = importlib.reload(module)
        second_type = reloaded_module.ReloadedRequest

        assert second_type is not first_type
        assert serialize_type(second_type) == serialized_name
        assert deserialize_type(serialized_name) is second_type
    finally:
        sys.modules.pop(module_name, None)


@pytest.mark.parametrize("serialized_name", ["", "int", ".int", "builtins..int", "builtins.int."])
def test_deserialize_type_rejects_malformed_names(serialized_name: str) -> None:
    """Malformed serialized names fail before compatibility lookup."""
    with pytest.raises(ValueError, match="Malformed serialized type name"):
        deserialize_type(serialized_name)


def test_deserialize_type_does_not_access_payload_selected_module_attributes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unknown names do not invoke module attribute hooks."""
    module_name = "_request_info_module_with_attribute_hook"
    accessed_attributes: list[str] = []

    class ObservableModule(ModuleType):
        def __getattribute__(self, name: str) -> Any:
            if name == "__dict__":
                accessed_attributes.append(name)
            return ModuleType.__getattribute__(self, name)

        def __getattr__(self, name: str) -> Any:
            accessed_attributes.append(name)
            raise AttributeError(name)

    selected_module = ObservableModule(module_name)
    monkeypatch.setitem(sys.modules, module_name, selected_module)

    with pytest.raises(AttributeError, match="has no attribute 'Attack'"):
        deserialize_type(f"{module_name}.Attack")

    assert accessed_attributes == []


def test_deserialize_type_error_handling() -> None:
    """Test error handling in deserialize_type function."""
    with pytest.raises(ModuleNotFoundError, match="No module named 'nonexistent.module'"):
        deserialize_type("nonexistent.module.Type")

    with pytest.raises(AttributeError, match="has no attribute 'NonExistentType'"):
        deserialize_type("builtins.NonExistentType")


def test_deserialize_type_requires_exact_loaded_module_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    """A loaded parent package does not turn an unloaded submodule into an attribute lookup."""
    importlib.import_module("xml")

    monkeypatch.delitem(sys.modules, "xml.not_loaded", raising=False)

    with pytest.raises(ModuleNotFoundError, match="No module named 'xml.not_loaded'"):
        deserialize_type("xml.not_loaded.Type")


def test_deserialize_type_does_not_import_unknown_module(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unknown serialized types must fail without importing payload-selected modules."""
    imported_modules: list[str] = []

    def track_import(module_name: str) -> None:
        imported_modules.append(module_name)

    monkeypatch.setattr(importlib, "import_module", track_import)

    with pytest.raises(ModuleNotFoundError, match="No module named 'untrusted_request_info_payload'"):
        deserialize_type("untrusted_request_info_payload.Attack")

    assert imported_modules == []


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
