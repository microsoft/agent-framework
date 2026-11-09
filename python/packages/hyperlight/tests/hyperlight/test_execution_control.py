# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import threading
from unittest.mock import Mock

import pytest


@pytest.mark.parametrize("concurrent_cold_execution", [6, 8], indirect=True)
async def test_cold_execution_excludes_queue_time_but_preserves_initialization_cost(concurrent_cold_execution) -> None:
    native = concurrent_cold_execution
    cold = asyncio.create_task(native.tool.invoke(arguments={"code": "cold"}))
    try:
        assert await asyncio.to_thread(native.initialized.wait, 2)
        other_tool = native.tool.create_run_tool()
        other_tool._execution_timeout_seconds = 100
        intervening = await asyncio.wait_for(other_tool.invoke(arguments={"code": "intervening"}), 2)
        assert intervening[0].text == "ok\n"
        assert native.cold_queued.is_set()
        result = await asyncio.wait_for(cold, 2)
        if native.duration > 7:
            assert result[0].type == "error"
            assert result[0].error_details == "Code execution exceeded its time limit."
        else:
            assert result[0].text == "ok\n"
        assert native.executed == ["None", "intervening", "cold"]
    finally:
        native.intervening_entered.set()
        native.cold_queued.set()
        await asyncio.gather(cold, return_exceptions=True)


@pytest.mark.parametrize("interrupted_initialization", ["build", "warmup", "snapshot"], indirect=True)
@pytest.mark.parametrize("signal", ["timeout", "cancellation"])
@pytest.mark.parametrize("include_detailed_errors", [False, True])
async def test_initialization_interruption_cleans_up_and_allows_recreation(
    interrupted_initialization, signal: str, include_detailed_errors: bool
) -> None:
    native = interrupted_initialization
    native.tool._include_detailed_errors = include_detailed_errors
    execution = asyncio.create_task(native.tool.invoke(arguments={"code": "guest"}))
    try:
        assert await asyncio.to_thread(native.entered.wait, 2)
        if signal == "timeout":
            native.clock.now += 11
        else:
            execution.cancel()
            assert await asyncio.to_thread(native.cancellation().wait, 2)
        native.release.set()
        if signal == "timeout":
            result = await asyncio.wait_for(execution, 2)
            assert len(result) == 1
            assert result[0].type == "error"
            assert result[0].error_details == "Code execution exceeded its time limit."
        else:
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(execution, 2)

        assert native.tool._registry._entries == {}
        assert not native.workers[0].is_alive()
        first_events = [(stage, ident) for generation, stage, ident in native.events if generation == 1]
        assert "drop" in [stage for stage, _ in first_events]
        assert "run" not in [stage for stage, _ in first_events]
        owner_threads = {ident for _, ident in first_events}
        assert len(owner_threads) == 1
        assert threading.get_ident() not in owner_threads
        if native.stage == "snapshot":
            assert "drop_snapshot" in [stage for stage, _ in first_events]

        recovered = await asyncio.wait_for(native.tool.invoke(arguments={"code": "guest"}), 2)
        assert recovered[0].text == "ok\n"
        assert len(native.tool._registry._entries) == 1
        assert any(generation == 2 and stage == "run" for generation, stage, _ in native.events)
    finally:
        native.release.set()
        native.interrupted.set()
        await asyncio.gather(execution, return_exceptions=True)


async def test_timeout_returns_error_and_allows_reuse(interruptible_execution) -> None:
    native = interruptible_execution
    result = await native.tool.invoke(arguments={"code": "guest"})

    assert native.completed.is_set()
    assert len(result) == 1
    assert result[0].type == "error"
    assert result[0].error_details == "Code execution exceeded its time limit."
    recovered = await native.tool.invoke(arguments={"code": "None"})
    assert recovered[0].text == "ok\n"


async def test_timeout_after_final_host_callback_returns_error_and_allows_reuse(
    interruptible_execution, execution_clock
) -> None:
    native = interruptible_execution
    execution = asyncio.create_task(native.tool.invoke(arguments={"code": "final_host"}))
    try:
        assert await asyncio.to_thread(native.entered.wait, 2)
        execution_clock.now += 1
        assert await asyncio.to_thread(native.kill_attempted.wait, 2)
        assert not execution.done()
        native.release.set()
        result = await asyncio.wait_for(execution, 2)
        assert native.completed.is_set()
        assert len(result) == 1
        assert result[0].type == "error"
        assert result[0].error_details == "Code execution exceeded its time limit."
        recovered = await native.tool.invoke(arguments={"code": "None"})
        assert recovered[0].text == "ok\n"
    finally:
        native.release.set()
        await asyncio.gather(execution, return_exceptions=True)


async def test_cancellation_before_default_executor_start_does_not_wait_or_create_sandbox(
    interruptible_execution, occupied_default_executor, monkeypatch: pytest.MonkeyPatch
) -> None:
    native = interruptible_execution
    pool = occupied_default_executor
    execute = Mock(wraps=native.tool._registry.execute)
    monkeypatch.setattr(native.tool._registry, "execute", execute)
    execution = asyncio.create_task(native.tool.invoke(arguments={"code": "None"}))
    try:
        await asyncio.wait_for(pool.queued.wait(), 2)
        assert not native.started.is_set()
        execution.cancel()
        done, _ = await asyncio.wait({execution}, timeout=0.5)
        assert done, "Queued cancellation waited for unrelated default-executor work."
        with pytest.raises(asyncio.CancelledError):
            await execution
        assert not pool.blocker.done()
        assert not native.started.is_set()
        assert not native.kill_attempted.is_set()
    finally:
        pool.release.set()
        await asyncio.gather(execution, return_exceptions=True)
        await asyncio.wait_for(pool.blocker, 2)
        await asyncio.get_running_loop().run_in_executor(None, lambda: None)
    assert not native.started.is_set()
    execute.assert_not_called()
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
