# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio


async def test_timeout_returns_error_and_allows_reuse(interruptible_execution) -> None:
    native = interruptible_execution
    result = await native.tool.invoke(arguments={"code": "guest"})

    assert native.completed.is_set()
    assert len(result) == 1
    assert result[0].type == "error"
    assert result[0].error_details == "Code execution exceeded its time limit."
    recovered = await native.tool.invoke(arguments={"code": "None"})
    assert recovered[0].text == "ok\n"


async def test_repeated_cancellation_waits_for_host_callback_to_finish(interruptible_execution) -> None:
    native = interruptible_execution
    execution = asyncio.create_task(native.tool.invoke(arguments={"code": "host"}))
    try:
        assert await asyncio.to_thread(native.entered.wait, 2)
        execution.cancel()
        assert await asyncio.to_thread(native.kill_attempted.wait, 2)
        execution.cancel()
        await asyncio.sleep(0)
        assert not execution.done()
        assert not native.completed.is_set()
    finally:
        native.release.set()
    try:
        await asyncio.wait_for(execution, 2)
    except asyncio.CancelledError:
        pass
    else:
        raise AssertionError("Caller cancellation was not preserved.")
    assert native.completed.is_set()
    recovered = await native.tool.invoke(arguments={"code": "None"})
    assert recovered[0].text == "ok\n"


async def test_queued_cancellation_does_not_interrupt_another_invocation(interruptible_execution) -> None:
    native = interruptible_execution
    native.tool._execution_timeout_seconds = 5
    active = asyncio.create_task(native.tool.invoke(arguments={"code": "host"}))
    queued = None
    try:
        assert await asyncio.to_thread(native.entered.wait, 2)
        queued = asyncio.create_task(native.tool.invoke(arguments={"code": "None"}))
        await asyncio.sleep(0.02)
        queued.cancel()
        await asyncio.sleep(0)
        assert not native.kill_attempted.is_set()
    finally:
        native.release.set()
        result = await asyncio.wait_for(active, 2)
    assert result[0].text == "ok\n"
    assert queued is not None
    try:
        await asyncio.wait_for(queued, 2)
    except asyncio.CancelledError:
        pass
    else:
        raise AssertionError("Queued cancellation was not preserved.")
    assert not native.kill_attempted.is_set()
