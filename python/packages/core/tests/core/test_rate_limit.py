# Copyright (c) Microsoft. All rights reserved.

"""Tests for per-tool token-bucket admission control."""

from collections.abc import Awaitable, Callable

import pytest

from agent_framework._middleware import FunctionInvocationContext
from agent_framework._rate_limit import ToolRateLimit, ToolRateLimitMiddleware
from agent_framework._tools import FunctionTool


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def make_context(name: str) -> FunctionInvocationContext:
    return FunctionInvocationContext(
        function=FunctionTool(
            name=name,
            description="Test tool",
            func=lambda: None,
        ),
        arguments={},
    )


async def invoke(
    middleware: ToolRateLimitMiddleware,
    name: str,
    execute: Callable[[], Awaitable[None]],
) -> FunctionInvocationContext:
    context = make_context(name)
    await middleware.process(context, execute)
    return context


@pytest.mark.asyncio
async def test_first_request_is_admitted() -> None:
    clock = FakeClock()
    limiter = ToolRateLimitMiddleware(
        {"search": ToolRateLimit(requests_per_second=1)},
        clock=clock,
    )
    executed = 0

    async def execute() -> None:
        nonlocal executed
        executed += 1

    context = await invoke(limiter, "search", execute)

    assert executed == 1
    assert context.result is None


@pytest.mark.asyncio
async def test_burst_exhaustion_rejects_without_execution() -> None:
    limiter = ToolRateLimitMiddleware(
        {"search": ToolRateLimit(requests_per_second=1, burst=2)},
        clock=FakeClock(),
    )
    executed = 0

    async def execute() -> None:
        nonlocal executed
        executed += 1

    await invoke(limiter, "search", execute)
    await invoke(limiter, "search", execute)
    rejected = await invoke(limiter, "search", execute)

    assert executed == 2
    assert "rate limit exceeded" in rejected.result.lower()


@pytest.mark.asyncio
async def test_tokens_refill_using_injected_clock() -> None:
    clock = FakeClock()
    limiter = ToolRateLimitMiddleware(
        {"search": ToolRateLimit(requests_per_second=2)},
        clock=clock,
    )
    executed = 0

    async def execute() -> None:
        nonlocal executed
        executed += 1

    await invoke(limiter, "search", execute)
    rejected = await invoke(limiter, "search", execute)
    assert "rate limit exceeded" in rejected.result.lower()

    clock.advance(0.5)
    admitted = await invoke(limiter, "search", execute)

    assert executed == 2
    assert admitted.result is None


@pytest.mark.asyncio
async def test_unconfigured_tool_is_unrestricted() -> None:
    limiter = ToolRateLimitMiddleware(
        {"search": ToolRateLimit(requests_per_second=1)},
        clock=FakeClock(),
    )
    executed = 0

    async def execute() -> None:
        nonlocal executed
        executed += 1

    for _ in range(5):
        await invoke(limiter, "other_tool", execute)

    assert executed == 5


@pytest.mark.parametrize(
    ("rate", "burst"),
    [
        (0, 1),
        (-1, 1),
        (float("nan"), 1),
        (float("inf"), 1),
        (1, 0),
        (1, -1),
        (1, True),
    ],
)
def test_invalid_configuration_is_rejected(rate: float, burst: int) -> None:
    with pytest.raises(ValueError):
        ToolRateLimit(requests_per_second=rate, burst=burst)


@pytest.mark.asyncio
async def test_concurrent_calls_cannot_exceed_burst() -> None:
    """Concurrent calls must reserve tokens atomically."""
    import asyncio

    clock = FakeClock()
    limiter = ToolRateLimitMiddleware(
        {"search": ToolRateLimit(requests_per_second=1, burst=3)},
        clock=clock,
    )

    executed = 0

    async def execute() -> None:
        nonlocal executed
        executed += 1
        await asyncio.sleep(0)

    results = await asyncio.gather(*(invoke(limiter, "search", execute) for _ in range(100)))

    admitted = sum(context.result is None for context in results)
    rejected = sum(
        isinstance(context.result, str) and "rate limit exceeded" in context.result.lower() for context in results
    )

    assert admitted == 3
    assert rejected == 97
    assert executed == 3


@pytest.mark.asyncio
async def test_independent_tool_quotas() -> None:
    """Exhausting one tool's quota must not affect another tool."""
    clock = FakeClock()
    limiter = ToolRateLimitMiddleware(
        {
            "search": ToolRateLimit(requests_per_second=1, burst=1),
            "database": ToolRateLimit(requests_per_second=2, burst=2),
        },
        clock=clock,
    )

    executions: list[str] = []

    async def execute_search() -> None:
        executions.append("search")

    async def execute_database() -> None:
        executions.append("database")

    first_search = await invoke(limiter, "search", execute_search)
    rejected_search = await invoke(limiter, "search", execute_search)

    first_database = await invoke(limiter, "database", execute_database)
    second_database = await invoke(limiter, "database", execute_database)
    rejected_database = await invoke(limiter, "database", execute_database)

    assert first_search.result is None
    assert "rate limit exceeded" in rejected_search.result.lower()

    assert first_database.result is None
    assert second_database.result is None
    assert "rate limit exceeded" in rejected_database.result.lower()

    assert executions == ["search", "database", "database"]


@pytest.mark.asyncio
async def test_cancellation_propagates_and_preserves_bucket_state() -> None:
    """Cancellation after admission propagates without corrupting the bucket."""
    import asyncio

    clock = FakeClock()
    limiter = ToolRateLimitMiddleware(
        {"search": ToolRateLimit(requests_per_second=1, burst=1)},
        clock=clock,
    )

    started = asyncio.Event()

    async def cancelled_tool() -> None:
        started.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(invoke(limiter, "search", cancelled_tool))
    await asyncio.wait_for(started.wait(), timeout=1)

    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    executions = 0

    async def execute() -> None:
        nonlocal executions
        executions += 1

    rejected = await invoke(limiter, "search", execute)

    assert executions == 0
    assert "rate limit exceeded" in rejected.result.lower()

    clock.advance(1.0)

    admitted = await invoke(limiter, "search", execute)

    assert admitted.result is None
    assert executions == 1


@pytest.mark.asyncio
async def test_backward_clock_does_not_create_tokens() -> None:
    """A backward clock jump must not replenish exhausted capacity."""
    clock = FakeClock()
    limiter = ToolRateLimitMiddleware(
        {"search": ToolRateLimit(requests_per_second=1, burst=1)},
        clock=clock,
    )

    executions = 0

    async def execute() -> None:
        nonlocal executions
        executions += 1

    await invoke(limiter, "search", execute)

    clock.advance(-10.0)
    rejected = await invoke(limiter, "search", execute)

    assert "rate limit exceeded" in rejected.result.lower()
    assert executions == 1

    clock.advance(10.0)
    still_rejected = await invoke(limiter, "search", execute)
    assert "rate limit exceeded" in still_rejected.result.lower()
    assert executions == 1

    clock.advance(1.0)
    admitted = await invoke(limiter, "search", execute)

    assert admitted.result is None
    assert executions == 2


@pytest.mark.asyncio
async def test_rate_limit_integrates_with_function_middleware_pipeline() -> None:
    """Rejected calls must not reach the pipeline's final handler."""
    from agent_framework._middleware import FunctionMiddlewarePipeline

    limiter = ToolRateLimitMiddleware(
        {"search": ToolRateLimit(requests_per_second=1, burst=1)},
        clock=FakeClock(),
    )
    pipeline = FunctionMiddlewarePipeline(limiter)

    executions = 0

    async def final_handler(context: FunctionInvocationContext) -> str:
        nonlocal executions
        executions += 1
        return "tool executed"

    first = make_context("search")
    first_result = await pipeline.execute(first, final_handler)

    second = make_context("search")
    second_result = await pipeline.execute(second, final_handler)

    assert first_result == "tool executed"
    assert isinstance(second_result, str)
    assert "rate limit exceeded" in second_result.lower()
    assert executions == 1


@pytest.mark.asyncio
async def test_rate_limit_auto_function_invocation() -> None:
    """Rate limiting must short-circuit real function invocation."""
    from agent_framework import Content, tool
    from agent_framework._middleware import FunctionMiddlewarePipeline
    from agent_framework._tools import (
        _auto_invoke_function,
        normalize_function_invocation_configuration,
    )

    executions = 0

    @tool(name="limited_search")
    def limited_search() -> str:
        nonlocal executions
        executions += 1
        return "search completed"

    limiter = ToolRateLimitMiddleware(
        {"limited_search": ToolRateLimit(requests_per_second=1, burst=1)},
        clock=FakeClock(),
    )
    pipeline = FunctionMiddlewarePipeline(limiter)
    config = normalize_function_invocation_configuration(None)
    tool_map = {limited_search.name: limited_search}

    first = await _auto_invoke_function(
        Content.from_function_call(
            call_id="rate-limit-first",
            name=limited_search.name,
            arguments={},
        ),
        config=config,
        tool_map=tool_map,
        middleware_pipeline=pipeline,
    )

    second = await _auto_invoke_function(
        Content.from_function_call(
            call_id="rate-limit-second",
            name=limited_search.name,
            arguments={},
        ),
        config=config,
        tool_map=tool_map,
        middleware_pipeline=pipeline,
    )

    assert first.type == "function_result"
    assert first.call_id == "rate-limit-first"
    assert first.result == "search completed"

    assert second.type == "function_result"
    assert second.call_id == "rate-limit-second"
    assert isinstance(second.result, str)
    assert "rate limit exceeded" in second.result.lower()

    assert executions == 1


@pytest.mark.parametrize("rate", [True, False])
def test_boolean_request_rates_are_rejected(rate: bool) -> None:
    """Boolean values must not be accepted as request rates."""
    with pytest.raises(ValueError, match="requests_per_second"):
        ToolRateLimit(requests_per_second=rate)
