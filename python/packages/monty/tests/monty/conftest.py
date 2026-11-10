# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio

import pytest
from agent_framework import FunctionTool


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
