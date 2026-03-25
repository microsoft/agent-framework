# Copyright (c) Microsoft. All rights reserved.

"""Tests for @tool with PEP 563 (from __future__ import annotations).

When ``from __future__ import annotations`` is active, all annotations
become strings.  _resolve_input_model must resolve them via
typing.get_type_hints() before passing them to Pydantic's create_model.
"""

from __future__ import annotations

from pydantic import BaseModel

from agent_framework import tool
from agent_framework._middleware import FunctionInvocationContext


class SearchConfig(BaseModel):
    max_results: int = 10


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
    assert params["properties"]["query"]["type"] == "string"
    limit_schema = params["properties"]["limit"]
    limit_types = {t["type"] for t in limit_schema["anyOf"]}
    assert limit_types == {"integer", "null"}


def test_tool_with_optional_param_and_context():
    """Optional param + FunctionInvocationContext both work under PEP 563."""

    @tool
    def search(query: str, limit: int | None = None, ctx: FunctionInvocationContext | None = None) -> str:
        """Search for something."""
        return query

    params = search.parameters()
    assert params["properties"]["query"]["type"] == "string"
    limit_schema = params["properties"]["limit"]
    limit_types = {t["type"] for t in limit_schema["anyOf"]}
    assert limit_types == {"integer", "null"}
    assert "ctx" not in params.get("properties", {})


def test_tool_with_optional_custom_type():
    """Optional[CustomType] is resolved under PEP 563 (original bug pattern)."""

    @tool
    def search(query: str, config: SearchConfig | None = None) -> str:
        """Search for something."""
        return query

    params = search.parameters()
    assert params["properties"]["query"]["type"] == "string"
    config_schema = params["properties"]["config"]
    config_types = [t.get("type") for t in config_schema["anyOf"]]
    assert "null" in config_types


def test_tool_with_unresolvable_forward_ref():
    """Fallback to raw annotations when get_type_hints() fails."""
    import types

    # Build a function in an isolated namespace so get_type_hints() cannot resolve
    # the forward reference, exercising the except-branch fallback.
    ns: dict = {}
    exec(
        "def greet(name: str = 'world') -> str:\n    '''Greet someone.'''\n    return f'Hello {name}'\n",
        ns,
    )
    func = ns["greet"]
    # Place the function in a throwaway module so get_type_hints() will fail on
    # any non-builtin forward ref while still having a valid __module__.
    mod = types.ModuleType("_phantom")
    func.__module__ = mod.__name__

    t = tool(func)
    params = t.parameters()
    assert params["properties"]["name"]["type"] == "string"


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
