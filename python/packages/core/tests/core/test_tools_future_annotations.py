# Copyright (c) Microsoft. All rights reserved.

"""Tests for @tool with PEP 563 (from __future__ import annotations).

When ``from __future__ import annotations`` is active, all annotations
become strings.  _resolve_input_model must resolve them via
typing.get_type_hints() before passing them to Pydantic's create_model.
"""

from __future__ import annotations

from agent_framework import tool
from agent_framework._middleware import FunctionInvocationContext


def test_tool_with_context_parameter():
    """FunctionInvocationContext parameter is excluded from schema under PEP 563."""

    @tool
    def get_weather(location: str, ctx: FunctionInvocationContext) -> str:
        """Get the weather for a given location."""
        return f"Weather in {location}"

    params = get_weather.parameters()
    assert "ctx" not in params.get("properties", {})
    assert "location" in params["properties"]


def test_tool_with_context_parameter_first():
    """FunctionInvocationContext as the first parameter is excluded under PEP 563."""

    @tool
    def get_weather(ctx: FunctionInvocationContext, location: str) -> str:
        """Get the weather for a given location."""
        return f"Weather in {location}"

    params = get_weather.parameters()
    assert "ctx" not in params.get("properties", {})
    assert "location" in params["properties"]


def test_tool_with_optional_param():
    """Optional[int] is resolved to the actual type, not left as a string."""

    @tool
    def search(query: str, limit: int | None = None) -> str:
        """Search for something."""
        return query

    params = search.parameters()
    assert "query" in params["properties"]
    assert "limit" in params["properties"]


def test_tool_with_optional_param_and_context():
    """Optional param + FunctionInvocationContext both work under PEP 563."""

    @tool
    def search(query: str, limit: int | None = None, ctx: FunctionInvocationContext = None) -> str:
        """Search for something."""
        return query

    params = search.parameters()
    assert "query" in params["properties"]
    assert "limit" in params["properties"]
    assert "ctx" not in params.get("properties", {})


async def test_tool_invoke_with_context():
    """Full invocation with FunctionInvocationContext under PEP 563."""

    @tool
    def get_weather(location: str, ctx: FunctionInvocationContext) -> str:
        """Get the weather for a given location."""
        user = ctx.kwargs.get("user", "anon")
        return f"Weather in {location} for {user}"

    params = get_weather.parameters()
    assert "ctx" not in params.get("properties", {})

    context = FunctionInvocationContext(
        function=get_weather,
        arguments=get_weather.input_model(location="Seattle"),
        kwargs={"user": "test_user"},
    )
    result = await get_weather.invoke(context=context)
    assert result[0].text == "Weather in Seattle for test_user"
