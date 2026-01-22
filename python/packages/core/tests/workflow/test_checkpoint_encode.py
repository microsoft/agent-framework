# Copyright (c) Microsoft. All rights reserved.

from dataclasses import dataclass
from typing import Any

from agent_framework._workflows._checkpoint_encoding import (
    _CYCLE_SENTINEL,
    DATACLASS_MARKER,
    MODEL_MARKER,
    encode_checkpoint_value,
)


@dataclass
class SimpleDataclass:
    """A simple dataclass for testing encoding."""

    name: str
    value: int


@dataclass
class NestedDataclass:
    """A dataclass with nested dataclass field."""

    outer_name: str
    inner: SimpleDataclass


class ModelWithToDict:
    """A class that implements to_dict/from_dict protocol."""

    def __init__(self, data: str) -> None:
        self.data = data

    def to_dict(self) -> dict[str, Any]:
        return {"data": self.data}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ModelWithToDict":
        return cls(data=d["data"])


class ModelWithToJson:
    """A class that implements to_json/from_json protocol."""

    def __init__(self, data: str) -> None:
        self.data = data

    def to_json(self) -> str:
        return f'{{"data": "{self.data}"}}'

    @classmethod
    def from_json(cls, json_str: str) -> "ModelWithToJson":
        import json

        d = json.loads(json_str)
        return cls(data=d["data"])


class UnknownObject:
    """A class that doesn't support any serialization protocol."""

    def __init__(self, value: str) -> None:
        self.value = value

    def __str__(self) -> str:
        return f"UnknownObject({self.value})"


# --- Tests for primitive encoding ---


def test_encode_string() -> None:
    """Test encoding a string value."""
    result = encode_checkpoint_value("hello")
    assert result == "hello"


def test_encode_integer() -> None:
    """Test encoding an integer value."""
    result = encode_checkpoint_value(42)
    assert result == 42


def test_encode_float() -> None:
    """Test encoding a float value."""
    result = encode_checkpoint_value(3.14)
    assert result == 3.14


def test_encode_boolean_true() -> None:
    """Test encoding a True boolean value."""
    result = encode_checkpoint_value(True)
    assert result is True


def test_encode_boolean_false() -> None:
    """Test encoding a False boolean value."""
    result = encode_checkpoint_value(False)
    assert result is False


def test_encode_none() -> None:
    """Test encoding a None value."""
    result = encode_checkpoint_value(None)
    assert result is None


# --- Tests for collection encoding ---


def test_encode_empty_dict() -> None:
    """Test encoding an empty dictionary."""
    result = encode_checkpoint_value({})
    assert result == {}


def test_encode_simple_dict() -> None:
    """Test encoding a simple dictionary with primitive values."""
    data = {"name": "test", "count": 5, "active": True}
    result = encode_checkpoint_value(data)
    assert result == {"name": "test", "count": 5, "active": True}


def test_encode_dict_with_non_string_keys() -> None:
    """Test encoding a dictionary with non-string keys (converted to strings)."""
    data = {1: "one", 2: "two"}
    result = encode_checkpoint_value(data)
    assert result == {"1": "one", "2": "two"}


def test_encode_empty_list() -> None:
    """Test encoding an empty list."""
    result = encode_checkpoint_value([])
    assert result == []


def test_encode_simple_list() -> None:
    """Test encoding a simple list with primitive values."""
    data = [1, 2, 3, "four"]
    result = encode_checkpoint_value(data)
    assert result == [1, 2, 3, "four"]


def test_encode_tuple() -> None:
    """Test encoding a tuple (converted to list)."""
    data = (1, 2, 3)
    result = encode_checkpoint_value(data)
    assert result == [1, 2, 3]


def test_encode_set() -> None:
    """Test encoding a set (converted to list)."""
    data = {1, 2, 3}
    result = encode_checkpoint_value(data)
    assert isinstance(result, list)
    assert sorted(result) == [1, 2, 3]


def test_encode_nested_dict() -> None:
    """Test encoding a nested dictionary structure."""
    data = {
        "outer": {
            "inner": {
                "value": 42,
            }
        }
    }
    result = encode_checkpoint_value(data)
    assert result == {"outer": {"inner": {"value": 42}}}


def test_encode_list_of_dicts() -> None:
    """Test encoding a list containing dictionaries."""
    data = [{"a": 1}, {"b": 2}]
    result = encode_checkpoint_value(data)
    assert result == [{"a": 1}, {"b": 2}]


# --- Tests for dataclass encoding ---


def test_encode_simple_dataclass() -> None:
    """Test encoding a simple dataclass."""
    obj = SimpleDataclass(name="test", value=42)
    result = encode_checkpoint_value(obj)

    assert isinstance(result, dict)
    assert DATACLASS_MARKER in result
    assert "value" in result
    assert result["value"] == {"name": "test", "value": 42}


def test_encode_nested_dataclass() -> None:
    """Test encoding a dataclass with nested dataclass fields."""
    inner = SimpleDataclass(name="inner", value=10)
    outer = NestedDataclass(outer_name="outer", inner=inner)
    result = encode_checkpoint_value(outer)

    assert isinstance(result, dict)
    assert DATACLASS_MARKER in result
    assert "value" in result

    outer_value = result["value"]
    assert outer_value["outer_name"] == "outer"
    assert DATACLASS_MARKER in outer_value["inner"]


def test_encode_list_of_dataclasses() -> None:
    """Test encoding a list containing dataclass instances."""
    data = [
        SimpleDataclass(name="first", value=1),
        SimpleDataclass(name="second", value=2),
    ]
    result = encode_checkpoint_value(data)

    assert isinstance(result, list)
    assert len(result) == 2
    for item in result:
        assert DATACLASS_MARKER in item


def test_encode_dict_with_dataclass_values() -> None:
    """Test encoding a dictionary with dataclass values."""
    data = {
        "item1": SimpleDataclass(name="first", value=1),
        "item2": SimpleDataclass(name="second", value=2),
    }
    result = encode_checkpoint_value(data)

    assert isinstance(result, dict)
    assert DATACLASS_MARKER in result["item1"]
    assert DATACLASS_MARKER in result["item2"]


# --- Tests for model protocol encoding ---


def test_encode_model_with_to_dict() -> None:
    """Test encoding an object implementing to_dict/from_dict protocol."""
    obj = ModelWithToDict(data="test_data")
    result = encode_checkpoint_value(obj)

    assert isinstance(result, dict)
    assert MODEL_MARKER in result
    assert result["strategy"] == "to_dict"
    assert result["value"] == {"data": "test_data"}


def test_encode_model_with_to_json() -> None:
    """Test encoding an object implementing to_json/from_json protocol."""
    obj = ModelWithToJson(data="test_data")
    result = encode_checkpoint_value(obj)

    assert isinstance(result, dict)
    assert MODEL_MARKER in result
    assert result["strategy"] == "to_json"
    assert '"data": "test_data"' in result["value"]


# --- Tests for unknown object encoding ---


def test_encode_unknown_object_fallback_to_string() -> None:
    """Test that unknown objects are encoded as strings."""
    obj = UnknownObject(value="test")
    result = encode_checkpoint_value(obj)

    assert isinstance(result, str)
    assert "UnknownObject" in result


# --- Tests for cycle detection ---


def test_encode_dict_with_self_reference() -> None:
    """Test that dict self-references are detected and handled."""
    data: dict[str, Any] = {"name": "test"}
    data["self"] = data  # Create circular reference

    result = encode_checkpoint_value(data)
    assert result["name"] == "test"
    assert result["self"] == _CYCLE_SENTINEL


def test_encode_list_with_self_reference() -> None:
    """Test that list self-references are detected and handled."""
    data: list[Any] = [1, 2]
    data.append(data)  # Create circular reference

    result = encode_checkpoint_value(data)
    assert result[0] == 1
    assert result[1] == 2
    assert result[2] == _CYCLE_SENTINEL


# --- Tests for reserved keyword handling ---
# Note: Security is enforced at deserialization time by validating class types,
# not at serialization time. This allows legitimate encoded data to be re-encoded.


def test_encode_allows_dict_with_model_marker_and_value() -> None:
    """Test that encoding a dict with MODEL_MARKER and 'value' is allowed.

    Security is enforced at deserialization time, not serialization time.
    """
    data = {
        MODEL_MARKER: "some.module:SomeClass",
        "value": {"data": "test"},
    }
    result = encode_checkpoint_value(data)
    assert MODEL_MARKER in result
    assert "value" in result


def test_encode_allows_dict_with_dataclass_marker_and_value() -> None:
    """Test that encoding a dict with DATACLASS_MARKER and 'value' is allowed.

    Security is enforced at deserialization time, not serialization time.
    """
    data = {
        DATACLASS_MARKER: "some.module:SomeClass",
        "value": {"field": "test"},
    }
    result = encode_checkpoint_value(data)
    assert DATACLASS_MARKER in result
    assert "value" in result


def test_encode_allows_nested_dict_with_marker_keys() -> None:
    """Test that encoding nested dict with marker keys is allowed.

    Security is enforced at deserialization time, not serialization time.
    """
    nested_data = {
        "outer": {
            MODEL_MARKER: "some.module:SomeClass",
            "value": {"data": "test"},
        }
    }
    result = encode_checkpoint_value(nested_data)
    assert "outer" in result
    assert MODEL_MARKER in result["outer"]


def test_encode_allows_marker_without_value() -> None:
    """Test that a dict with marker key but without 'value' key is allowed."""
    data = {
        MODEL_MARKER: "some.module:SomeClass",
        "other_key": "allowed",
    }
    result = encode_checkpoint_value(data)
    assert MODEL_MARKER in result
    assert result["other_key"] == "allowed"


def test_encode_allows_value_without_marker() -> None:
    """Test that a dict with 'value' key but without marker is allowed."""
    data = {
        "value": {"nested": "data"},
        "other_key": "allowed",
    }
    result = encode_checkpoint_value(data)
    assert "value" in result
    assert result["other_key"] == "allowed"


# --- Tests for max depth protection ---


def test_encode_deep_nesting_triggers_max_depth() -> None:
    """Test that very deep nesting triggers max depth protection."""
    # Create a deeply nested structure (over 100 levels)
    data: dict[str, Any] = {"level": 0}
    current = data
    for i in range(105):
        current["nested"] = {"level": i + 1}
        current = current["nested"]

    result = encode_checkpoint_value(data)

    # Navigate to find the max_depth sentinel
    current_result = result
    found_max_depth = False
    for _ in range(110):
        if isinstance(current_result, dict) and "nested" in current_result:
            current_result = current_result["nested"]
            if current_result == "<max_depth>":
                found_max_depth = True
                break
        else:
            break

    assert found_max_depth, "Expected <max_depth> sentinel to be found in deeply nested structure"


# --- Tests for mixed complex structures ---


def test_encode_complex_mixed_structure() -> None:
    """Test encoding a complex structure with mixed types."""
    data = {
        "string_value": "hello",
        "int_value": 42,
        "float_value": 3.14,
        "bool_value": True,
        "none_value": None,
        "list_value": [1, 2, 3],
        "nested_dict": {"a": 1, "b": 2},
        "dataclass_value": SimpleDataclass(name="test", value=100),
    }

    result = encode_checkpoint_value(data)

    assert result["string_value"] == "hello"
    assert result["int_value"] == 42
    assert result["float_value"] == 3.14
    assert result["bool_value"] is True
    assert result["none_value"] is None
    assert result["list_value"] == [1, 2, 3]
    assert result["nested_dict"] == {"a": 1, "b": 2}
    assert DATACLASS_MARKER in result["dataclass_value"]
