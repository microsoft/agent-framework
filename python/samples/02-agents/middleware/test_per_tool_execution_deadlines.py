# Copyright (c) Microsoft. All rights reserved.
"""Offline tests for the per-tool deadline middleware sample."""

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
from agent_framework import MiddlewareFailure
from per_tool_execution_deadlines import DeadlinePolicy, PerToolDeadlineMiddleware


def ctx(name: str = "tool") -> Any:
    return SimpleNamespace(function=SimpleNamespace(name=name), result=None)


@pytest.mark.parametrize("seconds", [0, -1, float("nan"), float("inf"), -float("inf")])
def test_invalid_deadline(seconds: float) -> None:
    with pytest.raises(ValueError, match="finite positive"):
        DeadlinePolicy(seconds)


@pytest.mark.asyncio
async def test_read_only_deadline_is_recoverable() -> None:
    mw = PerToolDeadlineMiddleware({"tool": DeadlinePolicy(0.01, read_only=True)})
    context = ctx()
    cleaned = asyncio.Event()

    async def slow() -> None:
        try:
            await asyncio.sleep(1)
        finally:
            cleaned.set()

    await mw.process(context, slow)
    assert "exceeded its deadline" in context.result
    assert cleaned.is_set()


@pytest.mark.asyncio
async def test_mutating_deadline_fails_closed() -> None:
    mw = PerToolDeadlineMiddleware({"tool": DeadlinePolicy(0.01)})

    async def slow() -> None:
        await asyncio.sleep(1)

    with pytest.raises(MiddlewareFailure, match="side effects may have occurred"):
        await mw.process(ctx(), slow)


@pytest.mark.asyncio
async def test_tool_timeout_is_not_deadline_expiry() -> None:
    mw = PerToolDeadlineMiddleware({"tool": DeadlinePolicy(1, read_only=True)})

    async def own_timeout() -> None:
        raise TimeoutError("tool's own timeout")

    with pytest.raises(TimeoutError, match="own timeout"):
        await mw.process(ctx(), own_timeout)


@pytest.mark.asyncio
async def test_caller_cancellation_propagates() -> None:
    mw = PerToolDeadlineMiddleware({"tool": DeadlinePolicy(1)})
    started = asyncio.Event()
    cleaned = asyncio.Event()

    async def slow() -> None:
        started.set()
        try:
            await asyncio.sleep(1)
        finally:
            cleaned.set()

    outer = asyncio.create_task(mw.process(ctx(), slow))
    await started.wait()
    outer.cancel()

    with pytest.raises(asyncio.CancelledError):
        await outer

    assert cleaned.is_set()


@pytest.mark.asyncio
async def test_independent_deadlines_concurrently() -> None:
    mw = PerToolDeadlineMiddleware({
        "fast": DeadlinePolicy(0.01, read_only=True),
        "slow": DeadlinePolicy(1, read_only=True),
    })
    fast, slow = ctx("fast"), ctx("slow")

    async def wait() -> None:
        await asyncio.sleep(0.03)

    await asyncio.gather(
        mw.process(fast, wait),
        mw.process(slow, wait),
    )
    assert "exceeded" in fast.result
    assert slow.result is None


@pytest.mark.asyncio
async def test_unconfigured_tool_passes_through() -> None:
    mw = PerToolDeadlineMiddleware({})
    called = False

    async def run() -> None:
        nonlocal called
        called = True

    await mw.process(ctx("unconfigured"), run)
    assert called


@pytest.mark.asyncio
async def test_normal_completion() -> None:
    mw = PerToolDeadlineMiddleware({"tool": DeadlinePolicy(1, read_only=True)})
    context = ctx()

    async def run() -> None:
        context.result = "ok"

    await mw.process(context, run)
    assert context.result == "ok"


@pytest.mark.asyncio
async def test_tool_exception_propagates() -> None:
    mw = PerToolDeadlineMiddleware({"tool": DeadlinePolicy(1, read_only=True)})

    async def fail() -> None:
        raise RuntimeError("tool failed")

    with pytest.raises(RuntimeError, match="tool failed"):
        await mw.process(ctx(), fail)


@pytest.mark.asyncio
async def test_mutating_timeout_does_not_cancel_sibling() -> None:
    mw = PerToolDeadlineMiddleware({
        "write": DeadlinePolicy(0.01),
        "read": DeadlinePolicy(1, read_only=True),
    })
    sibling_finished = asyncio.Event()

    async def write() -> None:
        await asyncio.sleep(1)

    async def read() -> None:
        await asyncio.sleep(0.03)
        sibling_finished.set()

    results = await asyncio.gather(
        mw.process(ctx("write"), write),
        mw.process(ctx("read"), read),
        return_exceptions=True,
    )

    assert isinstance(results[0], MiddlewareFailure)
    assert results[1] is None
    assert sibling_finished.is_set()


@pytest.mark.asyncio
async def test_caller_cancellation_with_delayed_cleanup() -> None:
    mw = PerToolDeadlineMiddleware({"tool": DeadlinePolicy(1)})
    started = asyncio.Event()
    cleanup_started = asyncio.Event()
    cleanup_finished = asyncio.Event()

    async def slow() -> None:
        started.set()
        try:
            await asyncio.sleep(10)
        finally:
            cleanup_started.set()
            await asyncio.sleep(0.02)
            cleanup_finished.set()

    outer = asyncio.create_task(mw.process(ctx(), slow))
    await started.wait()
    outer.cancel()

    with pytest.raises(asyncio.CancelledError):
        await outer

    await asyncio.wait_for(cleanup_finished.wait(), timeout=1)
    assert cleanup_started.is_set()


@pytest.mark.asyncio
async def test_timeout_does_not_retry_tool() -> None:
    mw = PerToolDeadlineMiddleware({"tool": DeadlinePolicy(0.01, read_only=True)})
    calls = 0

    async def slow() -> None:
        nonlocal calls
        calls += 1
        await asyncio.sleep(1)

    await mw.process(ctx(), slow)
    assert calls == 1


@pytest.mark.asyncio
async def test_timeout_cleanup_can_exceed_deadline() -> None:
    mw = PerToolDeadlineMiddleware({"tool": DeadlinePolicy(0.01, read_only=True)})
    cleaned = asyncio.Event()

    async def slow() -> None:
        try:
            await asyncio.sleep(1)
        finally:
            await asyncio.sleep(0.02)
            cleaned.set()

    await mw.process(ctx(), slow)
    assert cleaned.is_set()


@pytest.mark.asyncio
async def test_deadline_through_real_function_middleware_pipeline() -> None:
    """Exercise the framework pipeline rather than calling process directly."""
    from agent_framework._middleware import (
        FunctionInvocationContext,
        FunctionMiddlewarePipeline,
    )
    from agent_framework._tools import FunctionTool

    middleware = PerToolDeadlineMiddleware({"slow_tool": DeadlinePolicy(0.01, read_only=True)})
    pipeline = FunctionMiddlewarePipeline(middleware)
    function = FunctionTool(
        name="slow_tool",
        func=lambda: "unused",
        approval_mode="never_require",
    )
    context = FunctionInvocationContext(function=function, arguments={})

    calls = 0

    async def handler(ctx: FunctionInvocationContext) -> str:
        nonlocal calls
        calls += 1
        await asyncio.sleep(1)
        return "late result"

    result = await pipeline.execute(context, handler)

    assert result == "Read-only tool 'slow_tool' exceeded its deadline."
    assert calls == 1


@pytest.mark.asyncio
async def test_mutating_deadline_through_real_function_middleware_pipeline() -> None:
    """A side-effecting timeout must escape the pipeline as MiddlewareFailure."""
    from agent_framework._middleware import (
        FunctionInvocationContext,
        FunctionMiddlewarePipeline,
    )
    from agent_framework._tools import FunctionTool

    middleware = PerToolDeadlineMiddleware({"write_tool": DeadlinePolicy(0.01, read_only=False)})
    pipeline = FunctionMiddlewarePipeline(middleware)
    function = FunctionTool(
        name="write_tool",
        func=lambda: "unused",
        approval_mode="never_require",
    )
    context = FunctionInvocationContext(function=function, arguments={})

    async def handler(ctx: FunctionInvocationContext) -> str:
        await asyncio.sleep(1)
        return "unexpected"

    with pytest.raises(MiddlewareFailure, match="side effects may have occurred"):
        await pipeline.execute(context, handler)


@pytest.mark.asyncio
async def test_mutating_deadline_aborts_real_agent_concurrent_batch() -> None:
    """A mutating deadline aborts the batch and cancels an in-flight sibling."""
    import sys

    # Load the framework's existing mock-client fixture for this test.
    from agent_framework import Agent, ChatResponse, Content, Message
    from agent_framework._tools import FunctionTool

    tests_root = "packages/core/tests"
    if tests_root not in sys.path:
        sys.path.insert(0, tests_root)

    from core.conftest import MockBaseChatClient

    chat_client_base = MockBaseChatClient()

    sibling_started = asyncio.Event()
    sibling_cancelled = asyncio.Event()
    write_calls = 0

    async def write_impl(location: str) -> str:
        nonlocal write_calls
        write_calls += 1
        await sibling_started.wait()
        await asyncio.Event().wait()
        return "never"

    async def sibling_impl(location: str) -> str:
        sibling_started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            sibling_cancelled.set()
            raise
        return "never"

    write_tool = FunctionTool(
        name="write_tool",
        func=write_impl,
        approval_mode="never_require",
    )
    sibling_tool = FunctionTool(
        name="sibling_tool",
        func=sibling_impl,
        approval_mode="never_require",
    )

    chat_client_base.run_responses = [
        ChatResponse(
            messages=[
                Message(
                    role="assistant",
                    contents=[
                        Content.from_function_call(
                            call_id="call_1",
                            name="write_tool",
                            arguments='{"location": "Seattle"}',
                        ),
                        Content.from_function_call(
                            call_id="call_2",
                            name="sibling_tool",
                            arguments='{"location": "Seattle"}',
                        ),
                    ],
                )
            ]
        )
    ]

    middleware = PerToolDeadlineMiddleware({"write_tool": DeadlinePolicy(0.05, read_only=False)})

    agent = Agent(
        client=chat_client_base,
        middleware=[middleware],
        tools=[write_tool, sibling_tool],
    )

    with pytest.raises(
        MiddlewareFailure,
        match="side effects may have occurred",
    ):
        await asyncio.wait_for(agent.run("run both tools"), timeout=2)

    assert write_calls == 1
    assert sibling_cancelled.is_set()
    assert chat_client_base.call_count == 1
