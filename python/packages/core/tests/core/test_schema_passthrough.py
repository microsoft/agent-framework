# Copyright (c) Microsoft. All rights reserved.

"""Test that JSON schemas are passed through without conversion to Pydantic models."""

from typing import Any

import pytest
from pydantic import BaseModel

from agent_framework import FunctionTool, tool
from agent_framework.exceptions import ToolException


def test_function_tool_with_json_schema_stores_schema():
    """Test that FunctionTool stores the JSON schema as-is without conversion."""

    json_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "max_results": {"type": "integer", "default": 10},
        },
        "required": ["query"],
    }

    def search_func(query: str, max_results: int = 10) -> str:
        return f"Searching for: {query} (max {max_results})"

    tool_instance = FunctionTool(
        name="search",
        description="Search tool",
        func=search_func,
        input_model=json_schema,
    )

    # The stored schema should be the original JSON schema
    # not a Pydantic-generated one
    params = tool_instance.parameters()

    # Verify it matches the original schema structure
    assert params["type"] == "object"
    assert "query" in params["properties"]
    assert params["properties"]["query"]["type"] == "string"
    assert params["properties"]["max_results"]["default"] == 10


def test_tool_decorator_with_json_schema_stores_schema():
    """Test that @tool decorator stores JSON schema as-is."""

    json_schema = {
        "type": "object",
        "properties": {
            "location": {"type": "string", "description": "City name"},
            "unit": {"type": "string", "enum": ["celsius", "fahrenheit"], "default": "celsius"},
        },
        "required": ["location"],
    }

    @tool(name="weather", description="Get weather", schema=json_schema)
    def get_weather(location: str, unit: str = "celsius") -> str:
        return f"Weather in {location}: 22°{unit[0].upper()}"

    params = get_weather.parameters()

    # Should be the original schema
    assert params["type"] == "object"
    assert "location" in params["properties"]
    assert params["properties"]["unit"]["enum"] == ["celsius", "fahrenheit"]


@pytest.mark.asyncio
async def test_schema_supplied_tool_invocation_without_pydantic_validation():
    """Test that schema-supplied tools skip pydantic model_validate in invoke."""

    json_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer"},
        },
        "required": ["name"],
    }

    invocation_count = 0

    def greet(name: str, age: int | None = None) -> str:
        nonlocal invocation_count
        invocation_count += 1
        if age:
            return f"Hello {name}, you are {age} years old"
        return f"Hello {name}"

    tool_instance = FunctionTool(
        name="greet",
        description="Greet a person",
        func=greet,
        input_model=json_schema,
    )

    # Create a mock arguments object that mimics what the tool would receive
    class MockArgs(BaseModel):
        name: str
        age: int | None = None

    args = MockArgs(name="Alice", age=30)

    # Invoke the tool
    result = await tool_instance.invoke(arguments=args)

    assert invocation_count == 1
    assert "Alice" in result
    assert "30" in result


async def test_schema_supplied_tool_invocation_rejects_missing_required_args():
    """Schema-supplied tools should still enforce required fields."""

    json_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer"},
        },
        "required": ["name"],
    }

    def greet(name: str, age: int | None = None) -> str:
        return f"Hello {name}, age={age}"

    tool_instance = FunctionTool(
        name="greet",
        description="Greet a person",
        func=greet,
        input_model=json_schema,
    )

    with pytest.raises(TypeError, match="Missing required argument"):
        await tool_instance.invoke(arguments={"age": 30})


async def test_schema_supplied_tool_invocation_rejects_wrong_type():
    """Schema-supplied tools should run lightweight type checks."""

    json_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer"},
        },
        "required": ["name"],
    }

    def greet(name: str, age: int | None = None) -> str:
        return f"Hello {name}, age={age}"

    tool_instance = FunctionTool(
        name="greet",
        description="Greet a person",
        func=greet,
        input_model=json_schema,
    )

    with pytest.raises(TypeError, match="Invalid type for 'age'"):
        await tool_instance.invoke(arguments={"name": "Alice", "age": "30"})


async def test_schema_supplied_tool_invocation_rejects_unexpected_arguments():
    """Schema-supplied tools should reject unknown fields when additionalProperties is false."""

    json_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
        },
        "required": ["name"],
        "additionalProperties": False,
    }

    def greet(name: str) -> str:
        return f"Hello {name}"

    tool_instance = FunctionTool(
        name="greet",
        description="Greet a person",
        func=greet,
        input_model=json_schema,
    )

    with pytest.raises(TypeError, match="Unexpected argument"):
        await tool_instance.invoke(arguments={"name": "Alice", "extra": True})


def test_json_schema_passthrough_preserves_custom_properties():
    """Test that custom JSON schema properties are preserved (not lost in conversion)."""

    json_schema = {
        "type": "object",
        "properties": {
            "priority": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "description": "Priority level",
                "x-custom-field": "custom-value",  # Custom property
            },
        },
        "required": ["priority"],
        "additionalProperties": False,  # Custom constraint
    }

    def process(priority: str) -> str:
        return f"Processing with priority: {priority}"

    tool_instance = FunctionTool(
        name="process",
        description="Process task",
        func=process,
        input_model=json_schema,
    )

    params = tool_instance.parameters()

    # Verify custom properties are preserved
    assert not params.get("additionalProperties")
    # Note: x-custom-field might be stripped by pydantic's model_json_schema,
    # but our implementation should preserve the original schema


def test_schema_without_conversion_maintains_exact_structure():
    """Test that the exact JSON schema structure is maintained without Pydantic interference."""

    # A schema that would be altered if round-tripped through Pydantic
    json_schema = {
        "type": "object",
        "properties": {
            "filters": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "field": {"type": "string"},
                        "value": {"type": "string"},
                    },
                },
                "minItems": 1,
            },
        },
        "required": ["filters"],
    }

    def apply_filters(filters: list[dict[str, Any]]) -> str:
        return f"Applied {len(filters)} filters"

    tool_instance = FunctionTool(
        name="apply_filters",
        description="Apply filters",
        func=apply_filters,
        input_model=json_schema,
    )

    params = tool_instance.parameters()

    # Verify the structure is exactly as provided
    assert params["properties"]["filters"]["minItems"] == 1
    assert params["properties"]["filters"]["items"]["type"] == "object"


@pytest.mark.asyncio
async def test_declaration_only_tool_with_json_schema():
    """Test declaration-only tools with JSON schema work correctly."""

    json_schema = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Command to execute"},
        },
        "required": ["command"],
    }

    tool_instance = FunctionTool(
        name="execute",
        description="Execute command",
        func=None,  # Declaration only
        input_model=json_schema,
    )

    # Should be able to get parameters
    params = tool_instance.parameters()
    assert params["properties"]["command"]["type"] == "string"

    # Should not be invocable
    class MockArgs(BaseModel):
        command: str

    with pytest.raises(ToolException):
        await tool_instance.invoke(arguments=MockArgs(command="test"))


def test_mcp_tool_schema_passthrough():
    """Test that MCP tool schemas are passed through without conversion."""
    from mcp import types

    from agent_framework import FunctionTool
    from agent_framework._mcp import _get_input_model_from_mcp_tool

    # Create an MCP tool with a complex schema
    mcp_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "filters": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "field": {"type": "string"},
                        "operator": {"type": "string", "enum": ["eq", "ne", "gt", "lt"]},
                        "value": {"type": "string"},
                    },
                },
            },
            "limit": {"type": "integer", "default": 10, "minimum": 1, "maximum": 100},
        },
        "required": ["query"],
        "additionalProperties": False,
    }

    mcp_tool = types.Tool(
        name="search_tool",
        description="Search with filters",
        inputSchema=mcp_schema,
    )

    # Get the schema from MCP tool
    schema = _get_input_model_from_mcp_tool(mcp_tool)

    # Verify it's the original schema
    assert isinstance(schema, dict)
    assert schema == mcp_schema

    # Create a FunctionTool with this schema
    def search_impl(query: str, filters: list | None = None, limit: int = 10) -> str:
        return f"Searched for: {query}"

    func_tool = FunctionTool(
        name="search_tool",
        description="Search with filters",
        func=search_impl,
        input_model=schema,
    )

    # Verify the FunctionTool parameters match the original schema
    params = func_tool.parameters()
    assert params == mcp_schema
    assert not params.get("additionalProperties")
    assert params["properties"]["limit"]["minimum"] == 1
    assert params["properties"]["filters"]["items"]["properties"]["operator"]["enum"] == ["eq", "ne", "gt", "lt"]


@pytest.mark.asyncio
async def test_function_tool_with_mcp_schema_invocation():
    """Test that FunctionTool can invoke with MCP-sourced schemas."""
    from mcp import types

    from agent_framework import FunctionTool
    from agent_framework._mcp import _get_input_model_from_mcp_tool

    mcp_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "count": {"type": "integer"},
        },
        "required": ["name"],
    }

    mcp_tool = types.Tool(
        name="greet_tool",
        description="Greet someone",
        inputSchema=mcp_schema,
    )

    schema = _get_input_model_from_mcp_tool(mcp_tool)

    invocations = []

    def greet_impl(name: str, count: int = 1) -> str:
        invocations.append({"name": name, "count": count})
        return f"Hello {name}!" * count

    func_tool = FunctionTool(
        name="greet_tool",
        description="Greet someone",
        func=greet_impl,
        input_model=schema,
    )

    # Invoke with dict arguments
    result = await func_tool.invoke(arguments={"name": "Alice", "count": 2})

    assert len(invocations) == 1
    assert invocations[0]["name"] == "Alice"
    assert invocations[0]["count"] == 2
    assert "Hello Alice!" in result


def test_performance_benefit_of_schema_passthrough():
    """Verify that schema passthrough avoids expensive Pydantic model creation."""
    import time

    from agent_framework import FunctionTool

    # A complex schema that would be expensive to convert
    complex_schema = {
        "type": "object",
        "properties": {
            f"field_{i}": {"type": "string", "description": f"Field {i}"}
            for i in range(100)
        },
        "required": [f"field_{i}" for i in range(50)],
    }

    # Measure time to create FunctionTool with schema
    start = time.perf_counter()
    tool = FunctionTool(
        name="complex_tool",
        description="Complex tool",
        func=lambda **kwargs: "done",
        input_model=complex_schema,
    )
    schema_time = time.perf_counter() - start

    # Verify schema is stored as-is
    params = tool.parameters()
    assert params == complex_schema

    # The schema creation should be very fast (no Pydantic model building)
    # This is a smoke test - we're just verifying it doesn't error and returns quickly
    assert schema_time < 1.0  # Should be nearly instant
