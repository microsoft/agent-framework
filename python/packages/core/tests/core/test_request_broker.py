# Copyright (c) Microsoft. All rights reserved.

import asyncio

import pytest

from agent_framework import AsyncRequestBroker


async def test_resolve_delivers_result() -> None:
    broker: AsyncRequestBroker[str] = AsyncRequestBroker()
    task = asyncio.create_task(broker.request_async("r1"))
    await asyncio.sleep(0)
    assert broker.resolve("r1", "value") is True
    assert await task == "value"


async def test_reject_delivers_exception() -> None:
    broker: AsyncRequestBroker[str] = AsyncRequestBroker()
    task = asyncio.create_task(broker.request_async("r1"))
    await asyncio.sleep(0)
    assert broker.reject("r1", RuntimeError("boom")) is True
    with pytest.raises(RuntimeError, match="boom"):
        await task


async def test_timeout_raises() -> None:
    broker: AsyncRequestBroker[str] = AsyncRequestBroker()
    with pytest.raises(asyncio.TimeoutError):
        await broker.request_async("r1", timeout=0.001)
    assert broker.pending_count == 0


async def test_resolve_returns_false_when_not_found() -> None:
    broker: AsyncRequestBroker[str] = AsyncRequestBroker()
    assert broker.resolve("missing", "x") is False
    assert broker.reject("missing", RuntimeError("x")) is False


async def test_pending_count() -> None:
    broker: AsyncRequestBroker[int] = AsyncRequestBroker()
    task = asyncio.create_task(broker.request_async("r1"))
    await asyncio.sleep(0)
    assert broker.pending_count == 1
    broker.resolve("r1", 1)
    await task
    assert broker.pending_count == 0


async def test_duplicate_request_raises() -> None:
    broker: AsyncRequestBroker[int] = AsyncRequestBroker()
    task = asyncio.create_task(broker.request_async("r1"))
    await asyncio.sleep(0)
    with pytest.raises(ValueError, match="already pending"):
        await broker.request_async("r1")
    broker.resolve("r1", 1)
    await task
    with pytest.raises(ValueError, match="already settled"):
        await broker.request_async("r1")


async def test_resolve_and_reject_return_true_for_recently_settled_id() -> None:
    broker: AsyncRequestBroker[int] = AsyncRequestBroker()
    task = asyncio.create_task(broker.request_async("r1"))
    await asyncio.sleep(0)
    assert broker.resolve("r1", 1) is True
    assert await task == 1
    # Late duplicate responses for a recently settled ID are acknowledged.
    assert broker.resolve("r1", 2) is True
    assert broker.reject("r1", RuntimeError("late")) is True
    # Unknown IDs are still reported as not found.
    assert broker.resolve("unknown", 1) is False
    assert broker.reject("unknown", RuntimeError("x")) is False


async def test_evicted_settled_id_returns_false() -> None:
    broker: AsyncRequestBroker[int] = AsyncRequestBroker(settled_deque_size=1)
    for request_id in ("r1", "r2"):
        task = asyncio.create_task(broker.request_async(request_id))
        await asyncio.sleep(0)
        broker.resolve(request_id, 0)
        await task
    assert broker.resolve("r1", 1) is False
    assert broker.resolve("r2", 1) is True


async def test_timed_out_id_is_settled_and_cannot_be_reused() -> None:
    broker: AsyncRequestBroker[str] = AsyncRequestBroker()
    with pytest.raises(asyncio.TimeoutError):
        await broker.request_async("r1", timeout=0.001)
    # A late response for the expired request is acknowledged but not delivered.
    assert broker.resolve("r1", "stale") is True
    with pytest.raises(ValueError, match="already settled"):
        await broker.request_async("r1")
    assert broker.pending_count == 0


async def test_cancelled_id_is_settled_and_cannot_be_reused() -> None:
    broker: AsyncRequestBroker[str] = AsyncRequestBroker()
    task = asyncio.create_task(broker.request_async("r1"))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert broker.pending_count == 0
    assert broker.resolve("r1", "stale") is True
    with pytest.raises(ValueError, match="already settled"):
        await broker.request_async("r1")
    assert broker.pending_count == 0
