# Copyright (c) Microsoft. All rights reserved.

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from agent_framework._workflows._checkpoint_encoding import (
    _PICKLE_MARKER,
    _TYPE_MARKER,
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


class UnknownObject:
    """A class that doesn't support any serialization protocol."""

    def __init__(self, value: str) -> None:
        self.value = value

    def __str__(self) -> str:
        return f"UnknownObject({self.value})"


# --- Tests for primitive encoding (pass-through) ---


def test_encode_string() -> None:
    """Test encoding a string value."""
    assert encode_checkpoint_value("hello") == "hello"


def test_encode_integer() -> None:
    """Test encoding an integer value."""
    assert encode_checkpoint_value(42) == 42


def test_encode_float() -> None:
    """Test encoding a float value."""
    assert encode_checkpoint_value(3.14) == 3.14


def test_encode_boolean_true() -> None:
    """Test encoding a True boolean value."""
    assert encode_checkpoint_value(True) is True


def test_encode_boolean_false() -> None:
    """Test encoding a False boolean value."""
    assert encode_checkpoint_value(False) is False


def test_encode_none() -> None:
    """Test encoding a None value."""
    assert encode_checkpoint_value(None) is None


# --- Tests for collection encoding ---


def test_encode_empty_dict() -> None:
    """Test encoding an empty dictionary."""
    assert encode_checkpoint_value({}) == {}


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
    assert encode_checkpoint_value([]) == []


def test_encode_simple_list() -> None:
    """Test encoding a simple list with primitive values."""
    data = [1, 2, 3, "four"]
    result = encode_checkpoint_value(data)
    assert result == [1, 2, 3, "four"]


def test_encode_tuple() -> None:
    """Test encoding a tuple (pickled to preserve type)."""
    data = (1, 2, 3)
    result = encode_checkpoint_value(data)
    assert isinstance(result, dict)
    assert _PICKLE_MARKER in result
    assert _TYPE_MARKER in result


def test_encode_set() -> None:
    """Test encoding a set (pickled to preserve type)."""
    data = {1, 2, 3}
    result = encode_checkpoint_value(data)
    assert isinstance(result, dict)
    assert _PICKLE_MARKER in result
    assert _TYPE_MARKER in result


def test_encode_nested_dict() -> None:
    """Test encoding a nested dictionary structure."""
    data = {"outer": {"inner": {"value": 42}}}
    result = encode_checkpoint_value(data)
    assert result == {"outer": {"inner": {"value": 42}}}


def test_encode_list_of_dicts() -> None:
    """Test encoding a list containing dictionaries."""
    data = [{"a": 1}, {"b": 2}]
    result = encode_checkpoint_value(data)
    assert result == [{"a": 1}, {"b": 2}]


# --- Tests for non-JSON-native types (pickled) ---


def test_encode_simple_dataclass() -> None:
    """Test encoding a simple dataclass produces a pickled entry."""
    obj = SimpleDataclass(name="test", value=42)
    result = encode_checkpoint_value(obj)

    assert isinstance(result, dict)
    assert _PICKLE_MARKER in result
    assert _TYPE_MARKER in result
    assert isinstance(result[_PICKLE_MARKER], str)  # base64 string


def test_encode_nested_dataclass() -> None:
    """Test encoding a dataclass with nested dataclass fields."""
    inner = SimpleDataclass(name="inner", value=10)
    outer = NestedDataclass(outer_name="outer", inner=inner)
    result = encode_checkpoint_value(outer)

    assert isinstance(result, dict)
    assert _PICKLE_MARKER in result
    assert _TYPE_MARKER in result


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
        assert _PICKLE_MARKER in item


def test_encode_dict_with_dataclass_values() -> None:
    """Test encoding a dictionary with dataclass values."""
    data = {
        "item1": SimpleDataclass(name="first", value=1),
        "item2": SimpleDataclass(name="second", value=2),
    }
    result = encode_checkpoint_value(data)

    assert isinstance(result, dict)
    assert _PICKLE_MARKER in result["item1"]
    assert _PICKLE_MARKER in result["item2"]


def test_encode_model_with_to_dict() -> None:
    """Test encoding an object with to_dict is pickled (not using to_dict)."""
    obj = ModelWithToDict(data="test_data")
    result = encode_checkpoint_value(obj)

    assert isinstance(result, dict)
    assert _PICKLE_MARKER in result


def test_encode_unknown_object() -> None:
    """Test that arbitrary objects are pickled."""
    obj = UnknownObject(value="test")
    result = encode_checkpoint_value(obj)

    assert isinstance(result, dict)
    assert _PICKLE_MARKER in result


def test_encode_datetime() -> None:
    """Test that datetime objects are pickled."""
    dt = datetime(2024, 5, 4, 12, 30, 45, tzinfo=timezone.utc)
    result = encode_checkpoint_value(dt)

    assert isinstance(result, dict)
    assert _PICKLE_MARKER in result


# --- Tests for type marker ---


def test_encode_type_marker_records_type_info() -> None:
    """Test that encoded objects include correct type information."""
    obj = SimpleDataclass(name="test", value=42)
    result = encode_checkpoint_value(obj)

    type_key = result[_TYPE_MARKER]
    assert "SimpleDataclass" in type_key


def test_encode_type_marker_uses_module_qualname_format() -> None:
    """Test that type marker uses module:qualname format."""
    obj = SimpleDataclass(name="test", value=42)
    result = encode_checkpoint_value(obj)

    type_key = result[_TYPE_MARKER]
    assert ":" in type_key
    module, qualname = type_key.split(":")
    assert module  # non-empty module
    assert qualname == "SimpleDataclass"


# --- Tests for JSON serializability ---


def test_encode_result_is_json_serializable() -> None:
    """Test that encoded output is fully JSON-serializable."""
    data = {
        "dc": SimpleDataclass(name="test", value=42),
        "model": ModelWithToDict(data="test"),
        "dt": datetime.now(timezone.utc),
        "nested": [SimpleDataclass(name="n", value=1)],
    }

    result = encode_checkpoint_value(data)
    # Should not raise
    json_str = json.dumps(result)
    assert isinstance(json_str, str)


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

    # Primitives and collections pass through
    assert result["string_value"] == "hello"
    assert result["int_value"] == 42
    assert result["float_value"] == 3.14
    assert result["bool_value"] is True
    assert result["none_value"] is None
    assert result["list_value"] == [1, 2, 3]
    assert result["nested_dict"] == {"a": 1, "b": 2}
    # Dataclass is pickled
    assert _PICKLE_MARKER in result["dataclass_value"]


def test_encode_preserves_dict_with_pickle_marker_key() -> None:
    """Test that regular dicts containing _PICKLE_MARKER key are recursively encoded."""
    data = {
        _PICKLE_MARKER: "some_value",
        "other_key": "test",
    }
    result = encode_checkpoint_value(data)
    assert _PICKLE_MARKER in result
    assert result[_PICKLE_MARKER] == "some_value"
    assert result["other_key"] == "test"
