# Copyright (c) Microsoft. All rights reserved.

from agent_framework import AIFunction, AITool, ai_function


def test_ai_function_decorator():
    """Test the ai_function decorator."""

    @ai_function(name="test_tool", description="A test tool")
    def test_tool(x: int, y: int) -> int:
        """A simple function that adds two numbers."""
        return x + y

    assert isinstance(test_tool, AITool)
    assert isinstance(test_tool, AIFunction)
    assert test_tool.name == "test_tool"
    assert test_tool.description == "A test tool"
    assert test_tool.parameters() == {
        "properties": {"x": {"title": "X", "type": "integer"}, "y": {"title": "Y", "type": "integer"}},
        "required": ["x", "y"],
        "title": "test_tool_input",
        "type": "object",
    }
    assert test_tool(1, 2) == 3


def test_ai_function_decorator_without_args():
    """Test the ai_function decorator."""

    @ai_function
    def test_tool(x: int, y: int) -> int:
        """A simple function that adds two numbers."""
        return x + y

    assert isinstance(test_tool, AITool)
    assert isinstance(test_tool, AIFunction)
    assert test_tool.name == "test_tool"
    assert test_tool.description == "A simple function that adds two numbers."
    assert test_tool.parameters() == {
        "properties": {"x": {"title": "X", "type": "integer"}, "y": {"title": "Y", "type": "integer"}},
        "required": ["x", "y"],
        "title": "test_tool_input",
        "type": "object",
    }
    assert test_tool(1, 2) == 3


async def test_ai_function_decorator_with_async():
    """Test the ai_function decorator with an async function."""

    @ai_function(name="async_test_tool", description="An async test tool")
    async def async_test_tool(x: int, y: int) -> int:
        """An async function that adds two numbers."""
        return x + y

    assert isinstance(async_test_tool, AITool)
    assert isinstance(async_test_tool, AIFunction)
    assert async_test_tool.name == "async_test_tool"
    assert async_test_tool.description == "An async test tool"
    assert async_test_tool.parameters() == {
        "properties": {"x": {"title": "X", "type": "integer"}, "y": {"title": "Y", "type": "integer"}},
        "required": ["x", "y"],
        "title": "async_test_tool_input",
        "type": "object",
    }
    assert (await async_test_tool(1, 2)) == 3
