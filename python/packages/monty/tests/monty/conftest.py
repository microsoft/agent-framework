# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import pytest
from agent_framework import FunctionInvocationContext, FunctionTool, tool


@pytest.fixture
def host_error_detail() -> str:
    return "synthetic backend diagnostic"


@pytest.fixture
def failing_host_tool(request: pytest.FixtureRequest, host_error_detail: str) -> FunctionTool:
    def fail() -> str:
        raise ValueError(host_error_detail)

    async def fail_async() -> str:
        await asyncio.sleep(0)
        raise ValueError(host_error_detail)

    return FunctionTool(
        name="failing_host_tool",
        description="Raise a synthetic diagnostic.",
        func=fail_async if request.param else fail,
    )


@pytest.fixture
def cancelled_host_tool() -> FunctionTool:
    async def cancel() -> str:
        raise asyncio.CancelledError

    return FunctionTool(name="cancelled_host_tool", func=cancel)


@pytest.fixture
def recording_host_tool(request: pytest.FixtureRequest) -> tuple[FunctionTool, list[str | None]]:
    """Return a host tool and the labels it received; ``request.param`` selects the signature style."""
    calls: list[str | None] = []

    def positional_or_keyword(label: str | None = None) -> str:
        calls.append(label)
        return "recorded"

    def keyword_only(*, label: str | None = None) -> str:
        calls.append(label)
        return "recorded"

    host_tool = FunctionTool(
        name="record",
        description="Record the label received by the host.",
        func=keyword_only if request.param == "keyword_only" else positional_or_keyword,
    )
    return host_tool, calls


@pytest.fixture
def unsupplied_parameter_host_tool(request: pytest.FixtureRequest) -> tuple[FunctionTool, list[str]]:
    """Return a ``lookup`` host tool and the queries it received.

    ``request.param`` selects a parameter that guest code cannot supply: an injected context, ``**kwargs``,
    ``*args`` or ``self``. ``FunctionTool`` leaves each of them out of the parameters it accepts.
    """
    calls: list[str] = []

    def with_context(query: str, ctx: FunctionInvocationContext) -> str:
        calls.append(f"{query}:{type(ctx).__name__}")
        return "recorded"

    def with_var_keyword(query: str, **extra: Any) -> str:
        calls.append(query)
        return "recorded"

    def with_var_positional(query: str, *extra: str) -> str:
        calls.append(query)
        return "recorded"

    class Service:
        @tool(name="lookup")
        def lookup(self, query: str) -> str:
            calls.append(query)
            return "recorded"

    if request.param == "method":
        return Service().lookup, calls
    functions: dict[str, Callable[..., Any]] = {
        "context": with_context,
        "var_keyword": with_var_keyword,
        "var_positional": with_var_positional,
    }
    return FunctionTool(name="lookup", description="Record the query.", func=functions[request.param]), calls
