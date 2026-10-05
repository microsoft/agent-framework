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
