# Copyright (c) Microsoft. All rights reserved.

"""Tests for utilities."""

from dataclasses import dataclass
from datetime import date, datetime

from agent_framework_ag_ui._utils import generate_event_id, make_json_safe, merge_state


def test_generate_event_id():
    """Test event ID generation."""
    id1 = generate_event_id()
    id2 = generate_event_id()

    assert id1 != id2
    assert isinstance(id1, str)
    assert len(id1) > 0


def test_merge_state():
    """Test state merging."""
    current = {"a": 1, "b": 2}
    update = {"b": 3, "c": 4}

    result = merge_state(current, update)

    assert result["a"] == 1
    assert result["b"] == 3
    assert result["c"] == 4


def test_merge_state_empty_update():
    """Test merging with empty update."""
    current = {"x": 10, "y": 20}
    update = {}

    result = merge_state(current, update)

    assert result == current
    assert result is not current


def test_merge_state_empty_current():
    """Test merging with empty current state."""
    current = {}
    update = {"a": 1, "b": 2}

    result = merge_state(current, update)

    assert result == update


def test_make_json_safe_basic():
    """Test JSON serialization of basic types."""
    assert make_json_safe("text") == "text"
    assert make_json_safe(123) == 123
    assert make_json_safe(None) is None
    assert make_json_safe(3.14) == 3.14
    assert make_json_safe(True) is True
    assert make_json_safe(False) is False


def test_make_json_safe_datetime():
    """Test datetime serialization."""
    dt = datetime(2025, 10, 30, 12, 30, 45)
    result = make_json_safe(dt)
    assert result == "2025-10-30T12:30:45"


def test_make_json_safe_date():
    """Test date serialization."""
    d = date(2025, 10, 30)
    result = make_json_safe(d)
    assert result == "2025-10-30"


@dataclass
class SampleDataclass:
    """Sample dataclass for testing."""

    name: str
    value: int


def test_make_json_safe_dataclass():
    """Test dataclass serialization."""
    obj = SampleDataclass(name="test", value=42)
    result = make_json_safe(obj)
    assert result == {"name": "test", "value": 42}


class ModelDumpObject:
    """Object with model_dump method."""

    def model_dump(self):
        return {"type": "model", "data": "dump"}


def test_make_json_safe_model_dump():
    """Test object with model_dump method."""
    obj = ModelDumpObject()
    result = make_json_safe(obj)
    assert result == {"type": "model", "data": "dump"}


class DictObject:
    """Object with dict method."""

    def dict(self):
        return {"type": "dict", "method": "call"}


def test_make_json_safe_dict_method():
    """Test object with dict method."""
    obj = DictObject()
    result = make_json_safe(obj)
    assert result == {"type": "dict", "method": "call"}


class CustomObject:
    """Custom object with __dict__."""

    def __init__(self):
        self.field1 = "value1"
        self.field2 = 123


def test_make_json_safe_dict_attribute():
    """Test object with __dict__ attribute."""
    obj = CustomObject()
    result = make_json_safe(obj)
    assert result == {"field1": "value1", "field2": 123}


def test_make_json_safe_list():
    """Test list serialization."""
    lst = [1, "text", None, {"key": "value"}]
    result = make_json_safe(lst)
    assert result == [1, "text", None, {"key": "value"}]


def test_make_json_safe_tuple():
    """Test tuple serialization."""
    tpl = (1, 2, 3)
    result = make_json_safe(tpl)
    assert result == [1, 2, 3]


def test_make_json_safe_dict():
    """Test dict serialization."""
    d = {"a": 1, "b": {"c": 2}}
    result = make_json_safe(d)
    assert result == {"a": 1, "b": {"c": 2}}


def test_make_json_safe_nested():
    """Test nested structure serialization."""
    obj = {
        "datetime": datetime(2025, 10, 30),
        "list": [1, 2, CustomObject()],
        "nested": {"value": SampleDataclass(name="nested", value=99)},
    }
    result = make_json_safe(obj)

    assert result["datetime"] == "2025-10-30T00:00:00"
    assert result["list"][0] == 1
    assert result["list"][2] == {"field1": "value1", "field2": 123}
    assert result["nested"]["value"] == {"name": "nested", "value": 99}


class UnserializableObject:
    """Object that can't be serialized by standard methods."""

    def __init__(self):
        # Add attribute to trigger __dict__ fallback path
        pass


def test_make_json_safe_fallback():
    """Test fallback to dict for objects with __dict__."""
    obj = UnserializableObject()
    result = make_json_safe(obj)
    # Objects with __dict__ return their __dict__ dict
    assert isinstance(result, dict)
