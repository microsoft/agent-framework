# Copyright (c) Microsoft. All rights reserved.
from typing import Annotated, Any, Literal, get_args, get_origin
from unittest.mock import Mock

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic import BaseModel

from agent_framework import (
    Content,
    FunctionTool,
    tool,
)
from agent_framework._middleware import FunctionInvocationContext
from agent_framework._tools import (
    _parse_annotation,
    _parse_inputs,
)
from agent_framework.observability import OtelAttr

# region FunctionTool and tool decorator tests


def test_tool_decorator():
    """Test the tool decorator."""

    @tool(name="test_tool", description="A test tool")
    def test_tool(x: int, y: int) -> int:
        """A simple function that adds two numbers."""
        return x + y

    assert isinstance(test_tool, FunctionTool)
    assert test_tool.name == "test_tool"
    assert test_tool.description == "A test tool"
    assert test_tool.parameters() == {
        "properties": {"x": {"title": "X", "type": "integer"}, "y": {"title": "Y", "type": "integer"}},
        "required": ["x", "y"],
        "title": "test_tool_input",
        "type": "object",
    }
    assert test_tool(1, 2) == 3


def test_tool_decorator_without_args():
    """Test the tool decorator."""

    @tool
    def test_tool(x: int, y: int) -> int:
        """A simple function that adds two numbers."""
        return x + y

    assert isinstance(test_tool, FunctionTool)
    assert test_tool.name == "test_tool"
    assert test_tool.description == "A simple function that adds two numbers."
    assert test_tool.parameters() == {
        "properties": {"x": {"title": "X", "type": "integer"}, "y": {"title": "Y", "type": "integer"}},
        "required": ["x", "y"],
        "title": "test_tool_input",
        "type": "object",
    }
    assert test_tool(1, 2) == 3
    assert test_tool.approval_mode == "never_require"


def test_tool_decorator_with_pydantic_schema():
    """Test that the tool decorator accepts an explicit Pydantic model schema."""
    from pydantic import Field

    class MyInput(BaseModel):
        location: Annotated[str, Field(description="City name")]
        unit: str = "celsius"

    @tool(name="weather", description="Get weather", schema=MyInput)
    def get_weather(location: str, unit: str = "celsius") -> str:
        return f"{location}: {unit}"

    assert isinstance(get_weather, FunctionTool)
    assert get_weather.name == "weather"
    params = get_weather.parameters()
    assert "location" in params["properties"]
    assert params["properties"]["location"].get("description") == "City name"
    assert get_weather("Seattle") == "Seattle: celsius"
    assert get_weather("Seattle", "fahrenheit") == "Seattle: fahrenheit"


def test_tool_decorator_with_json_schema_dict():
    """Test that the tool decorator accepts an explicit JSON schema dict."""

    json_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "max_results": {"type": "integer", "default": 10},
        },
        "required": ["query"],
    }

    @tool(name="search", description="Search tool", schema=json_schema)
    def search(query: str, max_results: int = 10) -> str:
        return f"Searching for: {query} (max {max_results})"

    assert isinstance(search, FunctionTool)
    params = search.parameters()
    assert params["properties"]["query"]["type"] == "string"
    assert params["properties"]["query"]["description"] == "Search query"
    assert "max_results" in params["properties"]
    assert search("hello") == "Searching for: hello (max 10)"


async def test_tool_decorator_with_json_schema_invoke_uses_mapping():
    """Test that schema-based tools can be invoked directly with mapping arguments."""

    json_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer"},
        },
        "required": ["query"],
    }

    @tool(name="search", description="Search tool", schema=json_schema)
    def search(query: str, max_results: int = 10) -> str:
        return f"{query}:{max_results}"

    result = await search.invoke(arguments={"query": "hello", "max_results": 3})
    assert isinstance(result, list)
    assert result[0].text == "hello:3"


async def test_tool_decorator_with_json_schema_invoke_missing_required():
    """Test schema-required fields are checked for mapping arguments."""

    json_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
        },
        "required": ["query"],
    }

    @tool(name="search", description="Search tool", schema=json_schema)
    def search(query: str) -> str:
        return query

    with pytest.raises(TypeError, match="Missing required argument"):
        await search.invoke(arguments={})


async def test_tool_decorator_with_json_schema_invoke_invalid_type():
    """Test schema type checks run for mapping arguments."""

    json_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer"},
        },
        "required": ["query"],
    }

    @tool(name="search", description="Search tool", schema=json_schema)
    def search(query: str, max_results: int = 10) -> str:
        return f"{query}:{max_results}"

    with pytest.raises(TypeError, match="Invalid type for 'max_results'"):
        await search.invoke(arguments={"query": "hello", "max_results": "three"})


def test_tool_decorator_with_json_schema_preserves_custom_properties():
    """Test schema passthrough keeps custom JSON schema properties."""

    json_schema = {
        "type": "object",
        "properties": {
            "priority": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "x-custom-field": "custom-value",
            },
        },
        "required": ["priority"],
        "additionalProperties": False,
    }

    @tool(name="process", description="Process tool", schema=json_schema)
    def process(priority: str) -> str:
        return priority

    params = process.parameters()
    assert not params.get("additionalProperties")
    assert params["properties"]["priority"]["x-custom-field"] == "custom-value"


def test_tool_decorator_schema_none_default():
    """Test that schema=None (default) still infers from function signature."""

    @tool(name="adder", schema=None)
    def add(x: int, y: int) -> int:
        return x + y

    assert isinstance(add, FunctionTool)
    params = add.parameters()
    assert params == {
        "properties": {"x": {"title": "X", "type": "integer"}, "y": {"title": "Y", "type": "integer"}},
        "required": ["x", "y"],
        "title": "adder_input",
        "type": "object",
    }
    assert add(1, 2) == 3


async def test_tool_decorator_with_schema_invoke():
    """Test that invoke works correctly with explicit schema."""

    class CalcInput(BaseModel):
        a: int
        b: int

    @tool(name="calc", description="Calculator", schema=CalcInput)
    def calculate(a: int, b: int) -> int:
        return a + b

    result = await calculate.invoke(arguments=CalcInput(a=3, b=7))
    assert isinstance(result, list)
    assert result[0].text == "10"


def test_tool_decorator_with_schema_overrides_annotations():
    """Test that explicit schema completely overrides function signature inference."""
    from pydantic import Field

    class DetailedInput(BaseModel):
        location: Annotated[str, Field(description="The city and state")]
        unit: Annotated[str, Field(description="Temperature unit")] = "celsius"

    @tool(schema=DetailedInput)
    def get_weather(location: str, unit: str = "celsius") -> str:
        """Get weather for a location."""
        return f"{location}: {unit}"

    params = get_weather.parameters()
    assert params["properties"]["location"].get("description") == "The city and state"
    assert params["properties"]["unit"].get("description") == "Temperature unit"


def test_tool_without_args():
    """Test the tool decorator."""

    @tool
    def test_tool() -> int:
        """A simple function that adds two numbers."""
        return 1 + 2

    assert isinstance(test_tool, FunctionTool)
    assert isinstance(test_tool, FunctionTool)
    assert test_tool.name == "test_tool"
    assert test_tool.description == "A simple function that adds two numbers."
    assert test_tool.parameters() == {
        "properties": {},
        "title": "test_tool_input",
        "type": "object",
    }
    assert test_tool() == 3


async def test_tool_decorator_with_async():
    """Test the tool decorator with an async function."""

    @tool(name="async_test_tool", description="An async test tool")
    async def async_test_tool(x: int, y: int) -> int:
        """An async function that adds two numbers."""
        return x + y

    assert isinstance(async_test_tool, FunctionTool)
    assert async_test_tool.name == "async_test_tool"
    assert async_test_tool.description == "An async test tool"
    assert async_test_tool.parameters() == {
        "properties": {"x": {"title": "X", "type": "integer"}, "y": {"title": "Y", "type": "integer"}},
        "required": ["x", "y"],
        "title": "async_test_tool_input",
        "type": "object",
    }
    assert (await async_test_tool(1, 2)) == 3


def test_tool_decorator_in_class():
    """Test the tool decorator."""

    class my_tools:
        @tool(name="test_tool", description="A test tool")
        def test_tool(self, x: int, y: int) -> int:
            """A simple function that adds two numbers."""
            return x + y

    test_tool = my_tools().test_tool

    assert isinstance(test_tool, FunctionTool)
    assert test_tool.name == "test_tool"
    assert test_tool.description == "A test tool"
    assert test_tool.parameters() == {
        "properties": {"x": {"title": "X", "type": "integer"}, "y": {"title": "Y", "type": "integer"}},
        "required": ["x", "y"],
        "title": "test_tool_input",
        "type": "object",
    }
    assert test_tool(1, 2) == 3


def test_tool_with_literal_type_parameter():
    """Test tool decorator with Literal type parameter (issue #2891)."""

    @tool
    def search_flows(category: Literal["Data", "Security", "Network"], issue: str) -> str:
        """Search flows by category."""
        return f"{category}: {issue}"

    assert isinstance(search_flows, FunctionTool)
    schema = search_flows.parameters()
    assert schema == {
        "properties": {
            "category": {"enum": ["Data", "Security", "Network"], "title": "Category", "type": "string"},
            "issue": {"title": "Issue", "type": "string"},
        },
        "required": ["category", "issue"],
        "title": "search_flows_input",
        "type": "object",
    }
    # Verify invocation works
    assert search_flows("Data", "test issue") == "Data: test issue"


def test_tool_with_literal_type_in_class_method():
    """Test tool decorator with Literal type parameter in a class method (issue #2891)."""

    class MyTools:
        @tool
        def search_flows(self, category: Literal["Data", "Security", "Network"], issue: str) -> str:
            """Search flows by category."""
            return f"{category}: {issue}"

    tools = MyTools()
    search_tool = tools.search_flows
    assert isinstance(search_tool, FunctionTool)
    schema = search_tool.parameters()
    assert schema == {
        "properties": {
            "category": {"enum": ["Data", "Security", "Network"], "title": "Category", "type": "string"},
            "issue": {"title": "Issue", "type": "string"},
        },
        "required": ["category", "issue"],
        "title": "search_flows_input",
        "type": "object",
    }
    # Verify invocation works
    assert search_tool("Security", "test issue") == "Security: test issue"


def test_tool_with_literal_int_type():
    """Test tool decorator with Literal int type parameter."""

    @tool
    def set_priority(priority: Literal[1, 2, 3], task: str) -> str:
        """Set priority for a task."""
        return f"Priority {priority}: {task}"

    assert isinstance(set_priority, FunctionTool)
    schema = set_priority.parameters()
    assert schema == {
        "properties": {
            "priority": {"enum": [1, 2, 3], "title": "Priority", "type": "integer"},
            "task": {"title": "Task", "type": "string"},
        },
        "required": ["priority", "task"],
        "title": "set_priority_input",
        "type": "object",
    }
    assert set_priority(1, "important task") == "Priority 1: important task"


def test_tool_with_literal_and_annotated():
    """Test tool decorator with Literal type combined with Annotated for description."""

    @tool
    def categorize(
        category: Annotated[Literal["A", "B", "C"], "The category to assign"],
        name: str,
    ) -> str:
        """Categorize an item."""
        return f"{category}: {name}"

    assert isinstance(categorize, FunctionTool)
    schema = categorize.parameters()
    # Literal type inside Annotated should preserve enum values
    assert schema["properties"]["category"]["enum"] == ["A", "B", "C"]
    assert categorize("A", "test") == "A: test"


async def test_tool_decorator_shared_state():
    """Test that decorated methods maintain shared state across multiple calls and tool usage."""

    class StatefulCounter:
        """A class that maintains a counter and provides decorated methods to interact with it."""

        def __init__(self, initial_value: int = 0):
            self.counter = initial_value
            self.operation_log: list[str] = []

        @tool(name="increment", description="Increment the counter")
        def increment(self, amount: int) -> str:
            """Increment the counter by the given amount."""
            self.counter += amount
            self.operation_log.append(f"increment({amount})")
            return f"Counter incremented by {amount}. New value: {self.counter}"

        @tool(name="get_value", description="Get the current counter value")
        def get_value(self) -> str:
            """Get the current counter value."""
            self.operation_log.append("get_value()")
            return f"Current counter value: {self.counter}"

        @tool(name="multiply", description="Multiply the counter")
        def multiply(self, factor: int) -> str:
            """Multiply the counter by the given factor."""
            self.counter *= factor
            self.operation_log.append(f"multiply({factor})")
            return f"Counter multiplied by {factor}. New value: {self.counter}"

    # Create a single instance with shared state
    counter_instance = StatefulCounter(initial_value=10)

    # Get the decorated methods - these will be used by different "agents" or tools
    increment_tool = counter_instance.increment
    get_value_tool = counter_instance.get_value
    multiply_tool = counter_instance.multiply

    # Verify they are FunctionTool instances
    assert isinstance(increment_tool, FunctionTool)
    assert isinstance(get_value_tool, FunctionTool)
    assert isinstance(multiply_tool, FunctionTool)

    # Tool 1 (increment) is used
    result1 = increment_tool(5)
    assert result1 == "Counter incremented by 5. New value: 15"
    assert counter_instance.counter == 15

    # Tool 2 (get_value) sees the state change from tool 1
    result2 = get_value_tool()
    assert result2 == "Current counter value: 15"
    assert counter_instance.counter == 15

    # Tool 3 (multiply) modifies the shared state
    result3 = multiply_tool(3)
    assert result3 == "Counter multiplied by 3. New value: 45"
    assert counter_instance.counter == 45

    # Tool 2 (get_value) sees the state change from tool 3
    result4 = get_value_tool()
    assert result4 == "Current counter value: 45"
    assert counter_instance.counter == 45

    # Tool 1 (increment) sees the current state and modifies it
    result5 = increment_tool(10)
    assert result5 == "Counter incremented by 10. New value: 55"
    assert counter_instance.counter == 55

    # Verify the operation log shows all operations in order
    assert counter_instance.operation_log == [
        "increment(5)",
        "get_value()",
        "multiply(3)",
        "get_value()",
        "increment(10)",
    ]

    # Verify the parameters don't include 'self'
    assert increment_tool.parameters() == {
        "properties": {"amount": {"title": "Amount", "type": "integer"}},
        "required": ["amount"],
        "title": "increment_input",
        "type": "object",
    }
    assert multiply_tool.parameters() == {
        "properties": {"factor": {"title": "Factor", "type": "integer"}},
        "required": ["factor"],
        "title": "multiply_input",
        "type": "object",
    }
    assert get_value_tool.parameters() == {
        "properties": {},
        "title": "get_value_input",
        "type": "object",
    }

    # Test with invoke method as well (simulating agent execution)
    result6 = await increment_tool.invoke(amount=5)
    assert isinstance(result6, list)
    assert result6[0].text == "Counter incremented by 5. New value: 60"
    assert counter_instance.counter == 60

    result7 = await get_value_tool.invoke()
    assert isinstance(result7, list)
    assert result7[0].text == "Current counter value: 60"
    assert counter_instance.counter == 60


async def test_tool_invoke_telemetry_enabled(span_exporter: InMemorySpanExporter):
    """Test the tool invoke method with telemetry enabled."""

    @tool(
        name="telemetry_test_tool",
        description="A test tool for telemetry",
    )
    def telemetry_test_tool(x: int, y: int) -> int:
        """A function that adds two numbers for telemetry testing."""
        return x + y

    # Mock the histogram
    mock_histogram = Mock()
    telemetry_test_tool._invocation_duration_histogram = mock_histogram
    span_exporter.clear()
    # Call invoke
    result = await telemetry_test_tool.invoke(x=1, y=2, tool_call_id="test_call_id")

    # Verify result
    assert isinstance(result, list)
    assert result[0].text == "3"

    # Verify telemetry calls
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert OtelAttr.TOOL_EXECUTION_OPERATION.value in span.name
    assert "telemetry_test_tool" in span.name
    assert span.attributes[OtelAttr.TOOL_NAME] == "telemetry_test_tool"
    assert span.attributes[OtelAttr.TOOL_CALL_ID] == "test_call_id"
    assert span.attributes[OtelAttr.TOOL_TYPE] == "function"
    assert span.attributes[OtelAttr.TOOL_DESCRIPTION] == "A test tool for telemetry"
    assert span.attributes[OtelAttr.TOOL_ARGUMENTS] == '{"x": 1, "y": 2}'
    assert span.attributes[OtelAttr.TOOL_RESULT] == "3"

    # Verify histogram was called with correct attributes
    mock_histogram.record.assert_called_once()
    call_args = mock_histogram.record.call_args
    assert call_args[0][0] > 0  # duration should be positive
    attributes = call_args[1]["attributes"]
    assert attributes[OtelAttr.MEASUREMENT_FUNCTION_TAG_NAME] == "telemetry_test_tool"
    assert attributes[OtelAttr.TOOL_CALL_ID] == "test_call_id"


@pytest.mark.parametrize("enable_sensitive_data", [False], indirect=True)
async def test_tool_invoke_telemetry_sensitive_disabled(span_exporter: InMemorySpanExporter):
    """Test the tool invoke method with telemetry enabled."""

    @tool(
        name="telemetry_test_tool",
        description="A test tool for telemetry",
    )
    def telemetry_test_tool(x: int, y: int) -> int:
        """A function that adds two numbers for telemetry testing."""
        return x + y

    # Mock the histogram
    mock_histogram = Mock()
    telemetry_test_tool._invocation_duration_histogram = mock_histogram
    span_exporter.clear()
    # Call invoke
    result = await telemetry_test_tool.invoke(x=1, y=2, tool_call_id="test_call_id")

    # Verify result
    assert isinstance(result, list)
    assert result[0].text == "3"

    # Verify telemetry calls
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert OtelAttr.TOOL_EXECUTION_OPERATION.value in span.name
    assert "telemetry_test_tool" in span.name
    assert span.attributes[OtelAttr.TOOL_NAME] == "telemetry_test_tool"
    assert span.attributes[OtelAttr.TOOL_CALL_ID] == "test_call_id"
    assert span.attributes[OtelAttr.TOOL_TYPE] == "function"
    assert span.attributes[OtelAttr.TOOL_DESCRIPTION] == "A test tool for telemetry"
    assert OtelAttr.TOOL_ARGUMENTS not in span.attributes
    assert OtelAttr.TOOL_RESULT not in span.attributes

    # Verify histogram was called with correct attributes
    mock_histogram.record.assert_called_once()
    call_args = mock_histogram.record.call_args
    assert call_args[0][0] > 0  # duration should be positive
    attributes = call_args[1]["attributes"]
    assert attributes[OtelAttr.MEASUREMENT_FUNCTION_TAG_NAME] == "telemetry_test_tool"
    assert attributes[OtelAttr.TOOL_CALL_ID] == "test_call_id"


async def test_tool_invoke_ignores_additional_kwargs() -> None:
    """Ensure tools drop unknown kwargs when invoked with validated arguments."""

    @tool
    async def simple_tool(message: str) -> str:
        """Echo tool."""
        return message.upper()

    args = simple_tool.input_model(message="hello world")

    # These kwargs simulate runtime context passed through function invocation.
    result = await simple_tool.invoke(
        arguments=args,
        api_token="secret-token",
        options={"model_id": "dummy"},
    )

    assert isinstance(result, list)
    assert result[0].text == "HELLO WORLD"


async def test_tool_invoke_telemetry_with_pydantic_args(span_exporter: InMemorySpanExporter):
    """Test the tool invoke method with Pydantic model arguments."""

    @tool(
        name="pydantic_test_tool",
        description="A test tool with Pydantic args",
    )
    def pydantic_test_tool(x: int, y: int) -> int:
        """A function that adds two numbers using Pydantic args."""
        return x + y

    # Create arguments as Pydantic model instance
    args_model = pydantic_test_tool.input_model(x=5, y=10)

    mock_histogram = Mock()
    pydantic_test_tool._invocation_duration_histogram = mock_histogram
    span_exporter.clear()
    # Call invoke with Pydantic model
    result = await pydantic_test_tool.invoke(arguments=args_model, tool_call_id="pydantic_call")

    # Verify result
    assert isinstance(result, list)
    assert result[0].text == "15"
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert OtelAttr.TOOL_EXECUTION_OPERATION.value in span.name
    assert "pydantic_test_tool" in span.name
    assert span.attributes[OtelAttr.TOOL_NAME] == "pydantic_test_tool"
    assert span.attributes[OtelAttr.TOOL_CALL_ID] == "pydantic_call"
    assert span.attributes[OtelAttr.TOOL_TYPE] == "function"
    assert span.attributes[OtelAttr.TOOL_DESCRIPTION] == "A test tool with Pydantic args"
    assert span.attributes[OtelAttr.TOOL_ARGUMENTS] == '{"x": 5, "y": 10}'


async def test_tool_invoke_telemetry_with_exception(span_exporter: InMemorySpanExporter):
    """Test the tool invoke method with telemetry when an exception occurs."""

    @tool(
        name="exception_test_tool",
        description="A test tool that raises an exception",
    )
    def exception_test_tool(x: int, y: int) -> int:
        """A function that raises an exception for telemetry testing."""
        raise ValueError("Test exception for telemetry")

    mock_histogram = Mock()
    exception_test_tool._invocation_duration_histogram = mock_histogram
    span_exporter.clear()
    # Call invoke and expect exception
    with pytest.raises(ValueError, match="Test exception for telemetry"):
        await exception_test_tool.invoke(x=1, y=2, tool_call_id="exception_call")
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert OtelAttr.TOOL_EXECUTION_OPERATION.value in span.name
    assert "exception_test_tool" in span.name
    assert span.attributes[OtelAttr.TOOL_NAME] == "exception_test_tool"
    assert span.attributes[OtelAttr.TOOL_CALL_ID] == "exception_call"
    assert span.attributes[OtelAttr.TOOL_TYPE] == "function"
    assert span.attributes[OtelAttr.TOOL_DESCRIPTION] == "A test tool that raises an exception"
    assert span.attributes[OtelAttr.TOOL_ARGUMENTS] == '{"x": 1, "y": 2}'
    assert span.attributes[OtelAttr.ERROR_TYPE] == ValueError.__name__
    assert span.status.status_code == trace.StatusCode.ERROR

    # Verify histogram was called with error attributes
    mock_histogram.record.assert_called_once()
    call_args = mock_histogram.record.call_args
    attributes = call_args[1]["attributes"]
    assert attributes[OtelAttr.ERROR_TYPE] == ValueError.__name__


async def test_tool_invoke_telemetry_async_function(span_exporter: InMemorySpanExporter):
    """Test the tool invoke method with telemetry on async function."""

    @tool(
        name="async_telemetry_test",
        description="An async test tool for telemetry",
    )
    async def async_telemetry_test(x: int, y: int) -> int:
        """An async function for telemetry testing."""
        return x * y

    mock_histogram = Mock()
    async_telemetry_test._invocation_duration_histogram = mock_histogram
    span_exporter.clear()
    # Call invoke
    result = await async_telemetry_test.invoke(x=3, y=4, tool_call_id="async_call")

    # Verify result
    assert isinstance(result, list)
    assert result[0].text == "12"
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert OtelAttr.TOOL_EXECUTION_OPERATION.value in span.name
    assert "async_telemetry_test" in span.name
    assert span.attributes[OtelAttr.TOOL_NAME] == "async_telemetry_test"
    assert span.attributes[OtelAttr.TOOL_CALL_ID] == "async_call"
    assert span.attributes[OtelAttr.TOOL_TYPE] == "function"
    assert span.attributes[OtelAttr.TOOL_DESCRIPTION] == "An async test tool for telemetry"
    assert span.attributes[OtelAttr.TOOL_ARGUMENTS] == '{"x": 3, "y": 4}'

    # Verify histogram recording
    mock_histogram.record.assert_called_once()
    call_args = mock_histogram.record.call_args
    attributes = call_args[1]["attributes"]
    assert attributes[OtelAttr.MEASUREMENT_FUNCTION_TAG_NAME] == "async_telemetry_test"


async def test_tool_invoke_invalid_pydantic_args():
    """Test the tool invoke method with invalid Pydantic model arguments."""

    @tool(name="invalid_args_test", description="A test tool for invalid args")
    def invalid_args_test(x: int, y: int) -> int:
        """A function for testing invalid Pydantic args."""
        return x + y

    # Create a different Pydantic model
    class WrongModel(BaseModel):
        a: str
        b: str

    wrong_args = WrongModel(a="hello", b="world")

    # Call invoke with wrong model type
    with pytest.raises(TypeError, match="Expected invalid_args_test_input, got WrongModel"):
        await invalid_args_test.invoke(arguments=wrong_args)


def test_tool_serialization():
    """Test FunctionTool serialization and deserialization."""

    def serialize_test(x: int, y: int) -> int:
        """A function for testing serialization."""
        return x - y

    serialize_test_tool = tool(name="serialize_test", description="A test tool for serialization")(serialize_test)

    # Serialize to dict
    tool_dict = serialize_test_tool.to_dict()
    assert tool_dict["type"] == "function_tool"
    assert tool_dict["name"] == "serialize_test"
    assert tool_dict["description"] == "A test tool for serialization"
    assert tool_dict["input_model"] == {
        "properties": {"x": {"title": "X", "type": "integer"}, "y": {"title": "Y", "type": "integer"}},
        "required": ["x", "y"],
        "title": "serialize_test_input",
        "type": "object",
    }

    # Deserialize from dict
    restored_tool = FunctionTool.from_dict(tool_dict, dependencies={"function_tool": {"func": serialize_test}})
    assert isinstance(restored_tool, FunctionTool)
    assert restored_tool.name == "serialize_test"
    assert restored_tool.description == "A test tool for serialization"
    assert restored_tool.parameters() == serialize_test_tool.parameters()
    assert restored_tool(10, 4) == 6

    # Deserialize from dict with instance name
    restored_tool_2 = FunctionTool.from_dict(
        tool_dict, dependencies={"function_tool": {"name:serialize_test": {"func": serialize_test}}}
    )
    assert isinstance(restored_tool_2, FunctionTool)
    assert restored_tool_2.name == "serialize_test"
    assert restored_tool_2.description == "A test tool for serialization"
    assert restored_tool_2.parameters() == serialize_test_tool.parameters()
    assert restored_tool_2(10, 4) == 6


# region _parse_inputs tests


def test_parse_inputs_none():
    """Test _parse_inputs with None input."""
    result = _parse_inputs(None)
    assert result == []


def test_parse_inputs_string():
    """Test _parse_inputs with string input."""

    result = _parse_inputs("http://example.com")
    assert len(result) == 1
    assert result[0].type == "uri"
    assert result[0].uri == "http://example.com"
    assert result[0].media_type == "text/plain"


def test_parse_inputs_list_of_strings():
    """Test _parse_inputs with list of strings."""

    inputs = ["http://example.com", "https://test.org"]
    result = _parse_inputs(inputs)

    assert len(result) == 2
    assert all(item.type == "uri" for item in result)
    assert result[0].uri == "http://example.com"
    assert result[1].uri == "https://test.org"
    assert all(item.media_type == "text/plain" for item in result)


def test_parse_inputs_uri_dict():
    """Test _parse_inputs with URI dictionary."""

    input_dict = {"uri": "http://example.com", "media_type": "application/json"}
    result = _parse_inputs(input_dict)

    assert len(result) == 1
    assert result[0].type == "uri"
    assert result[0].uri == "http://example.com"
    assert result[0].media_type == "application/json"


def test_parse_inputs_hosted_file_dict():
    """Test _parse_inputs with hosted file dictionary."""

    input_dict = {"file_id": "file-123"}
    result = _parse_inputs(input_dict)

    assert len(result) == 1
    assert result[0].type == "hosted_file"
    assert result[0].file_id == "file-123"


def test_parse_inputs_hosted_vector_store_dict():
    """Test _parse_inputs with hosted vector store dictionary."""
    from agent_framework import Content

    input_dict = {"vector_store_id": "vs-789"}
    result = _parse_inputs(input_dict)

    assert len(result) == 1
    assert isinstance(result[0], Content)
    assert result[0].type == "hosted_vector_store"
    assert result[0].vector_store_id == "vs-789"


def test_parse_inputs_data_dict():
    """Test _parse_inputs with data dictionary."""

    input_dict = {"data": b"test data", "media_type": "application/octet-stream"}
    result = _parse_inputs(input_dict)

    assert len(result) == 1
    assert result[0].type == "data"
    assert result[0].uri == "data:application/octet-stream;base64,dGVzdCBkYXRh"
    assert result[0].media_type == "application/octet-stream"


def test_parse_inputs_ai_contents_instance():
    """Test _parse_inputs with Content instance."""

    text_content = Content.from_text(text="Hello, world!")
    result = _parse_inputs(text_content)

    assert len(result) == 1
    assert result[0].type == "text"
    assert result[0].text == "Hello, world!"


def test_parse_inputs_mixed_list():
    """Test _parse_inputs with mixed input types."""

    inputs = [
        "http://example.com",  # string
        {"uri": "https://test.org", "media_type": "text/html"},  # URI dict
        {"file_id": "file-456"},  # hosted file dict
        Content.from_text(text="Hello"),  # Content instance
    ]

    result = _parse_inputs(inputs)

    assert len(result) == 4
    assert result[0].type == "uri"
    assert result[0].uri == "http://example.com"
    assert result[1].type == "uri"
    assert result[1].uri == "https://test.org"
    assert result[1].media_type == "text/html"
    assert result[2].type == "hosted_file"
    assert result[2].file_id == "file-456"
    assert result[3].type == "text"
    assert result[3].text == "Hello"


def test_parse_inputs_unsupported_dict():
    """Test _parse_inputs with unsupported dictionary format."""
    input_dict = {"unsupported_key": "value"}

    with pytest.raises(ValueError, match="Unsupported input type"):
        _parse_inputs(input_dict)


def test_parse_inputs_unsupported_type():
    """Test _parse_inputs with unsupported input type."""
    with pytest.raises(TypeError, match="Unsupported input type: int"):
        _parse_inputs(123)


# endregion


async def test_ai_function_with_kwargs_injection():
    """Test that ai_function correctly handles kwargs injection and hides them from schema."""

    @tool
    def tool_with_kwargs(x: int, **kwargs: Any) -> str:
        """A tool that accepts kwargs."""
        user_id = kwargs.get("user_id", "unknown")
        return f"x={x}, user={user_id}"

    # Verify schema does not include kwargs
    assert tool_with_kwargs.parameters() == {
        "properties": {"x": {"title": "X", "type": "integer"}},
        "required": ["x"],
        "title": "tool_with_kwargs_input",
        "type": "object",
    }

    # Verify direct invocation works
    assert tool_with_kwargs(1, user_id="user1") == "x=1, user=user1"

    # Verify invoke works with injected args
    result = await tool_with_kwargs.invoke(
        arguments=tool_with_kwargs.input_model(x=5),
        user_id="user2",
    )
    assert isinstance(result, list)
    assert result[0].text == "x=5, user=user2"

    # Verify invoke works without injected args (uses default)
    result_default = await tool_with_kwargs.invoke(
        arguments=tool_with_kwargs.input_model(x=10),
    )
    assert isinstance(result_default, list)
    assert result_default[0].text == "x=10, user=unknown"


async def test_ai_function_with_explicit_invocation_context():
    """Test that invoke() can receive runtime kwargs via FunctionInvocationContext."""

    @tool
    def tool_with_context(x: int, ctx: FunctionInvocationContext) -> str:
        """A tool that accepts runtime context injection."""
        user_id = ctx.kwargs.get("user_id", "unknown")
        return f"x={x}, user={user_id}"

    assert tool_with_context.parameters() == {
        "properties": {"x": {"title": "X", "type": "integer"}},
        "required": ["x"],
        "title": "tool_with_context_input",
        "type": "object",
    }

    context = FunctionInvocationContext(
        function=tool_with_context,
        arguments=tool_with_context.input_model(x=7),
        kwargs={"user_id": "ctx-user"},
    )

    result = await tool_with_context.invoke(context=context)

    assert result[0].text == "x=7, user=ctx-user"


async def test_ai_function_with_typed_context_parameter_using_custom_name():
    """Test that typed context injection works for names other than ctx."""

    @tool
    def tool_with_runtime_context(x: int, runtime: FunctionInvocationContext) -> str:
        """A tool that uses a custom context parameter name."""
        user_id = runtime.kwargs.get("user_id", "unknown")
        return f"x={x}, user={user_id}"

    assert tool_with_runtime_context.parameters() == {
        "properties": {"x": {"title": "X", "type": "integer"}},
        "required": ["x"],
        "title": "tool_with_runtime_context_input",
        "type": "object",
    }

    context = FunctionInvocationContext(
        function=tool_with_runtime_context,
        arguments=tool_with_runtime_context.input_model(x=8),
        kwargs={"user_id": "runtime-user"},
    )

    result = await tool_with_runtime_context.invoke(context=context)

    assert result[0].text == "x=8, user=runtime-user"


async def test_ai_function_with_explicit_schema_and_untyped_ctx():
    """Test that explicit schemas allow an untyped ctx parameter."""

    class ToolInput(BaseModel):
        x: int

    @tool(schema=ToolInput)
    def tool_with_schema(x, ctx) -> str:
        """A tool with explicit schema and implicit ctx injection."""
        return f"x={x}, user={ctx.kwargs.get('user_id', 'unknown')}"

    context = FunctionInvocationContext(
        function=tool_with_schema,
        arguments=ToolInput(x=9),
        kwargs={"user_id": "schema-user"},
    )

    result = await tool_with_schema.invoke(context=context)

    assert result[0].text == "x=9, user=schema-user"


async def test_ai_function_with_explicit_schema_and_typed_ctx():
    """Test that explicit schemas also work with typed context injection."""

    class ToolInput(BaseModel):
        x: int

    @tool(schema=ToolInput)
    def tool_with_schema(x: int, runtime: FunctionInvocationContext) -> str:
        """A tool with explicit schema and typed context injection."""
        return f"x={x}, user={runtime.kwargs.get('user_id', 'unknown')}"

    context = FunctionInvocationContext(
        function=tool_with_schema,
        arguments=ToolInput(x=11),
        kwargs={"user_id": "typed-schema-user"},
    )

    result = await tool_with_schema.invoke(context=context)

    assert tool_with_schema.parameters() == ToolInput.model_json_schema()
    assert result[0].text == "x=11, user=typed-schema-user"


def test_ai_function_with_multiple_typed_context_parameters_fails():
    """Test that tools reject multiple typed FunctionInvocationContext parameters."""

    with pytest.raises(ValueError, match="multiple FunctionInvocationContext parameters"):

        @tool
        def invalid_tool(ctx_one: FunctionInvocationContext, ctx_two: FunctionInvocationContext) -> str:
            return f"{ctx_one.kwargs}-{ctx_two.kwargs}"


def test_ai_function_with_ctx_and_typed_context_parameter_fails():
    """Test that explicit-schema tools reject both implicit ctx and typed context parameters."""

    class ToolInput(BaseModel):
        x: int

    with pytest.raises(ValueError, match="multiple FunctionInvocationContext parameters"):

        @tool(schema=ToolInput)
        def invalid_tool(x, ctx, runtime: FunctionInvocationContext) -> str:
            return f"{x}-{ctx.kwargs}-{runtime.kwargs}"


# region _parse_annotation tests


def test_parse_annotation_with_literal_type():
    """Test that _parse_annotation returns Literal types unchanged (issue #2891)."""
    # Literal with string values
    literal_annotation = Literal["Data", "Security", "Network"]
    result = _parse_annotation(literal_annotation)
    assert result is literal_annotation
    assert get_origin(result) is Literal
    assert get_args(result) == ("Data", "Security", "Network")


def test_parse_annotation_with_literal_int_type():
    """Test that _parse_annotation returns Literal int types unchanged."""

    literal_annotation = Literal[1, 2, 3]
    result = _parse_annotation(literal_annotation)
    assert result is literal_annotation
    assert get_origin(result) is Literal
    assert get_args(result) == (1, 2, 3)


def test_parse_annotation_with_literal_bool_type():
    """Test that _parse_annotation returns Literal bool types unchanged."""

    literal_annotation = Literal[True, False]
    result = _parse_annotation(literal_annotation)
    assert result is literal_annotation
    assert get_origin(result) is Literal
    assert get_args(result) == (True, False)


def test_parse_annotation_with_simple_types():
    """Test that _parse_annotation returns simple types unchanged."""
    assert _parse_annotation(str) is str
    assert _parse_annotation(int) is int
    assert _parse_annotation(float) is float
    assert _parse_annotation(bool) is bool


def test_parse_annotation_with_annotated_and_literal():
    """Test that Annotated[Literal[...], description] works correctly."""

    # When Literal is inside Annotated, it should still be preserved
    annotated_literal = Annotated[Literal["A", "B", "C"], "The category"]
    result = _parse_annotation(annotated_literal)

    # The Annotated type should be preserved
    origin = get_origin(result)
    assert origin is Annotated

    args = get_args(result)
    # First arg is the Literal type
    literal_type = args[0]
    assert get_origin(literal_type) is Literal
    assert get_args(literal_type) == ("A", "B", "C")


# endregion
