# Copyright (c) Microsoft. All rights reserved.

"""Tests for utilities."""

from dataclasses import dataclass
from datetime import date, datetime

from agent_framework_ag_ui._utils import (
    generate_event_id,
    make_json_safe,
    merge_state,
    serialize_content_result,
)


def test_generate_event_id():
    """Test event ID generation."""
    id1 = generate_event_id()
    id2 = generate_event_id()

    assert id1 != id2
    assert isinstance(id1, str)
    assert len(id1) > 0


def test_merge_state():
    """Test state merging."""
    current: dict[str, int] = {"a": 1, "b": 2}
    update: dict[str, int] = {"b": 3, "c": 4}

    result = merge_state(current, update)

    assert result["a"] == 1
    assert result["b"] == 3
    assert result["c"] == 4


def test_merge_state_empty_update():
    """Test merging with empty update."""
    current: dict[str, int] = {"x": 10, "y": 20}
    update: dict[str, int] = {}

    result = merge_state(current, update)

    assert result == current
    assert result is not current


def test_merge_state_empty_current():
    """Test merging with empty current state."""
    current: dict[str, int] = {}
    update: dict[str, int] = {"a": 1, "b": 2}

    result = merge_state(current, update)

    assert result == update


def test_merge_state_deep_copy():
    """Test that merge_state creates a deep copy preventing mutation of original."""
    current: dict[str, dict[str, object]] = {"recipe": {"name": "Cake", "ingredients": ["flour", "sugar"]}}
    update: dict[str, str] = {"other": "value"}

    result = merge_state(current, update)

    result["recipe"]["ingredients"].append("eggs")

    assert "eggs" not in current["recipe"]["ingredients"]
    assert current["recipe"]["ingredients"] == ["flour", "sugar"]
    assert result["recipe"]["ingredients"] == ["flour", "sugar", "eggs"]


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


def test_convert_tools_to_agui_format_with_ai_function():
    """Test converting AIFunction to AG-UI format."""
    from agent_framework import ai_function

    from agent_framework_ag_ui._utils import convert_tools_to_agui_format

    @ai_function
    def test_func(param: str, count: int = 5) -> str:
        """Test function."""
        return f"{param} {count}"

    result = convert_tools_to_agui_format([test_func])

    assert result is not None
    assert len(result) == 1
    assert result[0]["name"] == "test_func"
    assert result[0]["description"] == "Test function."
    assert "parameters" in result[0]
    assert "properties" in result[0]["parameters"]


def test_convert_tools_to_agui_format_with_callable():
    """Test converting plain callable to AG-UI format."""
    from agent_framework_ag_ui._utils import convert_tools_to_agui_format

    def plain_func(x: int) -> int:
        """A plain function."""
        return x * 2

    result = convert_tools_to_agui_format([plain_func])

    assert result is not None
    assert len(result) == 1
    assert result[0]["name"] == "plain_func"
    assert result[0]["description"] == "A plain function."
    assert "parameters" in result[0]


def test_convert_tools_to_agui_format_with_dict():
    """Test converting dict tool to AG-UI format."""
    from agent_framework_ag_ui._utils import convert_tools_to_agui_format

    tool_dict = {
        "name": "custom_tool",
        "description": "Custom tool",
        "parameters": {"type": "object"},
    }

    result = convert_tools_to_agui_format([tool_dict])

    assert result is not None
    assert len(result) == 1
    assert result[0] == tool_dict


def test_convert_tools_to_agui_format_with_none():
    """Test converting None tools."""
    from agent_framework_ag_ui._utils import convert_tools_to_agui_format

    result = convert_tools_to_agui_format(None)

    assert result is None


def test_convert_tools_to_agui_format_with_single_tool():
    """Test converting single tool (not in list)."""
    from agent_framework import ai_function

    from agent_framework_ag_ui._utils import convert_tools_to_agui_format

    @ai_function
    def single_tool(arg: str) -> str:
        """Single tool."""
        return arg

    result = convert_tools_to_agui_format(single_tool)

    assert result is not None
    assert len(result) == 1
    assert result[0]["name"] == "single_tool"


def test_convert_tools_to_agui_format_with_multiple_tools():
    """Test converting multiple tools."""
    from agent_framework import ai_function

    from agent_framework_ag_ui._utils import convert_tools_to_agui_format

    @ai_function
    def tool1(x: int) -> int:
        """Tool 1."""
        return x

    @ai_function
    def tool2(y: str) -> str:
        """Tool 2."""
        return y

    result = convert_tools_to_agui_format([tool1, tool2])

    assert result is not None
    assert len(result) == 2
    assert result[0]["name"] == "tool1"
    assert result[1]["name"] == "tool2"


# Tests for serialize_content_result


def test_serialize_content_result_none():
    """Test serializing None returns empty string."""
    result = serialize_content_result(None)
    assert result == ""


def test_serialize_content_result_dict():
    """Test serializing dict returns JSON string."""
    result = serialize_content_result({"key": "value", "number": 42})
    assert result == '{"key": "value", "number": 42}'


def test_serialize_content_result_empty_list():
    """Test serializing empty list returns empty string."""
    result = serialize_content_result([])
    assert result == ""


def test_serialize_content_result_single_text_content():
    """Test serializing single TextContent-like object returns plain text."""

    class MockTextContent:
        def __init__(self, text: str):
            self.text = text

    result = serialize_content_result([MockTextContent("Hello, world!")])
    assert result == "Hello, world!"


def test_serialize_content_result_multiple_text_contents():
    """Test serializing multiple TextContent-like objects returns JSON array."""

    class MockTextContent:
        def __init__(self, text: str):
            self.text = text

    result = serialize_content_result([MockTextContent("First"), MockTextContent("Second")])
    assert result == '["First", "Second"]'


def test_serialize_content_result_model_dump_object():
    """Test serializing object with model_dump method."""

    class MockModel:
        def model_dump(self, mode: str = "python"):
            return {"type": "model", "value": 123}

    result = serialize_content_result([MockModel()])
    # Single item should be the JSON string of the model dump
    assert result == '{"type": "model", "value": 123}'


def test_serialize_content_result_multiple_model_dump_objects():
    """Test serializing multiple objects with model_dump method."""

    class MockModel:
        def __init__(self, value: int):
            self._value = value

        def model_dump(self, mode: str = "python"):
            return {"value": self._value}

    result = serialize_content_result([MockModel(1), MockModel(2)])
    assert result == '["{\\"value\\": 1}", "{\\"value\\": 2}"]'


def test_serialize_content_result_string_fallback():
    """Test serializing objects without text or model_dump falls back to str()."""

    class PlainObject:
        def __str__(self):
            return "plain_object_str"

    result = serialize_content_result([PlainObject()])
    assert result == "plain_object_str"


def test_serialize_content_result_mixed_list():
    """Test serializing list with mixed content types."""

    class MockTextContent:
        def __init__(self, text: str):
            self.text = text

    class PlainObject:
        def __str__(self):
            return "plain"

    result = serialize_content_result([MockTextContent("text1"), PlainObject()])
    assert result == '["text1", "plain"]'


def test_serialize_content_result_string():
    """Test serializing plain string returns the string."""
    result = serialize_content_result("just a string")
    assert result == "just a string"


def test_serialize_content_result_number():
    """Test serializing number returns string representation."""
    result = serialize_content_result(42)
    assert result == "42"
