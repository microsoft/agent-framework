# Copyright (c) Microsoft. All rights reserved.
"""Offline regression tests for the per-tool rate-limit sample."""

import asyncio
import importlib.util
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

_SAMPLE = Path(__file__).resolve().parents[4] / "samples/02-agents/middleware/per_tool_rate_limiting.py"

_SPEC = importlib.util.spec_from_file_location("_per_tool_rate_limiting_sample", _SAMPLE)
assert _SPEC is not None and _SPEC.loader is not None

_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)

PerToolRateLimitMiddleware = _MODULE.PerToolRateLimitMiddleware
RatePolicy = _MODULE.RatePolicy


def context(name: str = "lookup") -> Any:
    return SimpleNamespace(function=SimpleNamespace(name=name), result=None)


@pytest.mark.parametrize(
    "capacity,refill", [(0, 1), (-1, 1), (1, 0), (1, -1), (1, float("inf")), (1, float("nan")), (True, 1)]
)
def test_invalid_policy(capacity: int, refill: float) -> None:
    with pytest.raises(ValueError):
        RatePolicy(capacity, refill)


def test_refill_and_independent_tool_quotas() -> None:
    mw = PerToolRateLimitMiddleware({"a": RatePolicy(1, 1), "b": RatePolicy(2, 1)})
    assert mw.admit("a", now=10)
    assert not mw.admit("a", now=10)
    assert mw.admit("b", now=10)
    assert mw.admit("b", now=10)
    assert not mw.admit("b", now=10)
    assert mw.admit("a", now=11)
    assert mw.admit("unconfigured", now=11)


def test_partial_refill_and_clock_rollback() -> None:
    mw = PerToolRateLimitMiddleware({"a": RatePolicy(1, 0.5)})
    assert mw.admit("a", now=10)
    assert not mw.admit("a", now=11)
    assert not mw.admit("a", now=9)
    assert mw.admit("a", now=12)


def test_thread_safe_admission() -> None:
    mw = PerToolRateLimitMiddleware({"a": RatePolicy(7, 0.000001)})
    with ThreadPoolExecutor(max_workers=24) as pool:
        results = list(pool.map(lambda _: mw.admit("a", now=100), range(200)))
    assert sum(results) == 7


@pytest.mark.asyncio
async def test_concurrent_invocations_never_exceed_capacity() -> None:
    mw = PerToolRateLimitMiddleware({"a": RatePolicy(3, 0.000001)})
    called = 0

    async def one() -> str | None:
        nonlocal called
        ctx = context("a")

        async def execute() -> None:
            nonlocal called
            called += 1
            await asyncio.sleep(0)
            ctx.result = "ok"

        await mw.process(ctx, execute)
        return ctx.result

    results = await asyncio.gather(*(one() for _ in range(50)))
    assert called == 3
    assert results.count("ok") == 3
    assert sum("rate limited" in r for r in results if r is not None) == 47


@pytest.mark.asyncio
async def test_rejection_before_side_effects() -> None:
    mw = PerToolRateLimitMiddleware({"a": RatePolicy(1, 0.000001)})
    called = 0

    async def execute() -> None:
        nonlocal called
        called += 1

    first, second = context("a"), context("a")
    await mw.process(first, execute)
    await mw.process(second, execute)
    assert called == 1
    assert "rate limited" in second.result


def test_reuse_across_separate_event_loops() -> None:
    mw = PerToolRateLimitMiddleware({"a": RatePolicy(1, 0.000001)})

    async def run() -> str | None:
        ctx = context("a")

        async def execute() -> None:
            ctx.result = "ok"

        await mw.process(ctx, execute)
        return ctx.result

    assert asyncio.run(run()) == "ok"
    assert "rate limited" in asyncio.run(run())


@pytest.mark.asyncio
async def test_caller_cancellation_is_not_swallowed() -> None:
    mw = PerToolRateLimitMiddleware({"a": RatePolicy(1, 1)})
    started = asyncio.Event()

    async def execute() -> None:
        started.set()
        await asyncio.sleep(3600)

    task = asyncio.create_task(mw.process(context("a"), execute))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_tool_exception_is_not_swallowed() -> None:
    mw = PerToolRateLimitMiddleware({"a": RatePolicy(1, 1)})

    async def execute() -> None:
        raise RuntimeError("tool failure")

    with pytest.raises(RuntimeError, match="tool failure"):
        await mw.process(context("a"), execute)


@pytest.mark.asyncio
async def test_real_framework_context_and_pipeline() -> None:
    """Exercise the framework's actual context, tool and middleware pipeline."""
    from agent_framework import FunctionInvocationContext, tool
    from agent_framework._middleware import FunctionMiddlewarePipeline

    calls: list[str] = []

    @tool(approval_mode="never_require")
    def lookup(query: str) -> str:
        calls.append(query)
        return f"found:{query}"

    limiter = PerToolRateLimitMiddleware({"lookup": RatePolicy(1, 0.000001)})
    pipeline = FunctionMiddlewarePipeline(limiter)

    async def invoke(query: str) -> Any:
        ctx = FunctionInvocationContext(function=lookup, arguments={"query": query})

        async def execute(current: FunctionInvocationContext) -> Any:
            return await current.function.invoke(arguments=current.arguments)

        await pipeline.execute(ctx, execute)
        return ctx.result

    admitted = await invoke("first")
    rejected = await invoke("second")
    assert calls == ["first"]
    assert admitted is not None
    assert isinstance(rejected, str)
    assert "rate limited" in rejected


@pytest.mark.asyncio
async def test_rejected_call_does_not_run_other_middleware_or_tool() -> None:
    from agent_framework import FunctionInvocationContext, FunctionMiddleware, tool
    from agent_framework._middleware import FunctionMiddlewarePipeline

    events: list[str] = []

    @tool(approval_mode="never_require")
    def lookup(query: str) -> str:
        events.append("tool")
        return query

    class Downstream(FunctionMiddleware):
        async def process(self, context: FunctionInvocationContext, call_next: Any) -> None:
            events.append("downstream")
            await call_next()

    pipeline = FunctionMiddlewarePipeline(PerToolRateLimitMiddleware({"lookup": RatePolicy(1, 0.000001)}), Downstream())

    async def invoke() -> Any:
        ctx = FunctionInvocationContext(function=lookup, arguments={"query": "x"})

        async def execute(current: FunctionInvocationContext) -> Any:
            return await current.function.invoke(arguments=current.arguments)

        await pipeline.execute(ctx, execute)
        return ctx.result

    await invoke()
    assert events == ["downstream", "tool"]
    rejected = await invoke()
    assert events == ["downstream", "tool"]
    assert "rate limited" in rejected


def test_clock_sampled_only_after_acquiring_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A contending caller must sample time after acquiring the lock."""
    import threading
    import time

    limiter = PerToolRateLimitMiddleware({"lookup": RatePolicy(1, 1.0)})

    # Start with one available token at t=100.
    assert limiter.admit("lookup", now=100)
    assert limiter.admit("lookup", now=101)

    clock_called = threading.Event()
    result: list[bool] = []

    def fake_monotonic() -> float:
        clock_called.set()
        return 102.0

    monkeypatch.setattr(time, "monotonic", fake_monotonic)

    def attempt() -> None:
        result.append(limiter.admit("lookup"))

    with limiter._lock:
        worker = threading.Thread(target=attempt)
        worker.start()

        # While the lock is held, the worker must not sample time.
        assert not clock_called.wait(timeout=0.1)

    worker.join(timeout=2)
    assert not worker.is_alive()
    assert result == [True]
    assert clock_called.is_set()

    # No second admission at the same timestamp.
    assert not limiter.admit("lookup", now=102)
