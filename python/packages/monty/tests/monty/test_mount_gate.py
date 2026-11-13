# Copyright (c) Microsoft. All rights reserved.

"""Behavior of the gate that makes calls to the same writable mount take turns."""

from __future__ import annotations

import asyncio
import copy
import pickle
import threading

import pytest

from agent_framework_monty import _mount_gate as gate_module
from agent_framework_monty._mount_gate import MountGate, MountGateTimeoutError


async def test_calls_take_turns_in_arrival_order() -> None:
    gate = MountGate()
    order: list[str] = []
    active = 0
    peak = 0

    async def call(name: str) -> None:
        nonlocal active, peak
        async with gate.hold():
            active += 1
            peak = max(peak, active)
            order.append(name)
            await asyncio.sleep(0.01)
            active -= 1

    tasks: list[asyncio.Task[None]] = []
    for name in ("first", "second", "third"):
        tasks.append(asyncio.create_task(call(name)))
        # Let each call queue before the next one starts.
        await asyncio.sleep(0)
    async with asyncio.timeout(10):
        await asyncio.gather(*tasks)

    assert order == ["first", "second", "third"]
    assert peak == 1


async def test_calls_take_turns_across_event_loops_and_threads(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gate_module, "WAIT_TIMEOUT_SECS", 30.0)
    gate = MountGate()
    release_first = asyncio.Event()
    other_loop: list[asyncio.AbstractEventLoop] = []
    other_loop_started = threading.Event()
    state_lock = threading.Lock()
    entered: list[str] = []
    active = 0
    peak = 0

    def enter(name: str) -> None:
        nonlocal active, peak
        with state_lock:
            active += 1
            peak = max(peak, active)
            entered.append(name)

    def leave() -> None:
        nonlocal active
        with state_lock:
            active -= 1

    async def first_call() -> None:
        async with gate.hold():
            enter("first")
            await release_first.wait()
            leave()

    async def call_from_another_loop() -> None:
        other_loop.append(asyncio.get_running_loop())
        other_loop_started.set()
        async with gate.hold():
            enter("another loop")
            await asyncio.sleep(0.01)
            leave()

    async def later_call_on_this_loop() -> None:
        async with gate.hold():
            enter("later")
            leave()

    async with asyncio.timeout(60):
        first = asyncio.create_task(first_call())
        await asyncio.sleep(0)
        other = asyncio.create_task(asyncio.to_thread(asyncio.run, call_from_another_loop()))
        await asyncio.to_thread(other_loop_started.wait, 30)
        # The other loop finishes the step in which its call queued before it runs this coroutine.
        await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(asyncio.sleep(0), other_loop[0]))
        later = asyncio.create_task(later_call_on_this_loop())
        await asyncio.sleep(0)

        release_first.set()
        await asyncio.gather(first, other, later)

    assert entered == ["first", "another loop", "later"]
    assert peak == 1


async def test_call_fails_when_its_turn_does_not_come_in_time(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gate_module, "WAIT_TIMEOUT_SECS", 0.2)
    gate = MountGate()
    release = asyncio.Event()

    async def holder() -> None:
        async with gate.hold():
            await release.wait()

    holding = asyncio.create_task(holder())
    await asyncio.sleep(0)

    async with asyncio.timeout(10):
        with pytest.raises(MountGateTimeoutError, match="Timed out after 0.2 seconds"):
            async with gate.hold():
                pytest.fail("The turn must not be granted while another call holds it.")
        release.set()
        await holding
        # The failed call left the queue, and the gate is free again.
        async with gate.hold():
            pass

    assert not gate._waiters


async def test_cancelled_waiter_leaves_the_queue_without_losing_the_turn() -> None:
    gate = MountGate()
    release = asyncio.Event()
    ran: list[str] = []

    async def holder() -> None:
        async with gate.hold():
            await release.wait()

    async def waiter(name: str) -> None:
        async with gate.hold():
            ran.append(name)

    holding = asyncio.create_task(holder())
    await asyncio.sleep(0)
    cancelled = asyncio.create_task(waiter("cancelled"))
    survivor = asyncio.create_task(waiter("survivor"))
    await asyncio.sleep(0)
    cancelled.cancel()
    release.set()

    async with asyncio.timeout(10):
        await asyncio.gather(holding, survivor)
        with pytest.raises(asyncio.CancelledError):
            await cancelled

    assert ran == ["survivor"]


async def test_waiter_cancelled_after_the_turn_was_handed_to_it_passes_the_turn_on() -> None:
    gate = MountGate()
    await gate._acquire()
    ran: list[str] = []

    async def waiter(name: str) -> None:
        async with gate.hold():
            ran.append(name)

    cancelled = asyncio.create_task(waiter("cancelled"))
    survivor = asyncio.create_task(waiter("survivor"))
    await asyncio.sleep(0)
    # The release hands the turn to the first waiter, whose task has been cancelled but has not run yet.
    cancelled.cancel()
    gate._release()

    async with asyncio.timeout(10):
        await survivor
        with pytest.raises(asyncio.CancelledError):
            await cancelled

    assert ran == ["survivor"]


async def test_release_skips_a_waiter_whose_event_loop_is_closed() -> None:
    gate = MountGate()
    await gate._acquire()
    closed_loop = asyncio.new_event_loop()
    abandoned = closed_loop.create_future()
    closed_loop.close()
    gate._waiters.append((closed_loop, abandoned))
    ran: list[str] = []

    async def waiter() -> None:
        async with gate.hold():
            ran.append("live")

    live = asyncio.create_task(waiter())
    await asyncio.sleep(0)
    gate._release()

    async with asyncio.timeout(10):
        await live

    assert ran == ["live"]


async def test_call_made_while_holding_the_gate_does_not_wait_for_it(monkeypatch: pytest.MonkeyPatch) -> None:
    # A failure here would make the nested calls wait, so keep it short.
    monkeypatch.setattr(gate_module, "WAIT_TIMEOUT_SECS", 5.0)
    gate = MountGate()

    async def nested_call() -> None:
        async with gate.hold():
            pass

    async with asyncio.timeout(30):
        async with gate.hold():
            async with gate.hold():
                pass
            await asyncio.create_task(nested_call())
            await asyncio.gather(nested_call(), nested_call())
            await asyncio.to_thread(asyncio.run, nested_call())


async def test_turn_lasts_until_a_call_started_inside_it_has_ended() -> None:
    gate = MountGate()
    background_holds = asyncio.Event()
    finish_background = asyncio.Event()
    entered: list[str] = []

    async def background_call() -> None:
        async with gate.hold():
            background_holds.set()
            await finish_background.wait()

    async def later_call() -> None:
        async with gate.hold():
            entered.append("later")

    async with asyncio.timeout(10):
        async with gate.hold():
            background = asyncio.create_task(background_call())
            await background_holds.wait()
    later = asyncio.create_task(later_call())
    # The call that had the turn has ended, but the call it started has not. A call that wrongly got the turn
    # would have entered by now.
    await asyncio.sleep(0.05)
    assert entered == []

    finish_background.set()
    async with asyncio.timeout(10):
        await asyncio.gather(background, later)

    assert entered == ["later"]


async def test_call_started_by_a_running_call_after_the_turn_holder_ended_does_not_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A failure here would make the nested call wait, so keep it short.
    monkeypatch.setattr(gate_module, "WAIT_TIMEOUT_SECS", 5.0)
    gate = MountGate()
    background_holds = asyncio.Event()
    holder_ended = asyncio.Event()

    async def background_call() -> None:
        async with gate.hold():
            background_holds.set()
            await holder_ended.wait()
            async with gate.hold():
                pass

    async with asyncio.timeout(30):
        async with gate.hold():
            background = asyncio.create_task(background_call())
            await background_holds.wait()
        holder_ended.set()
        await background


async def test_call_that_outlives_the_hold_that_started_it_waits_for_its_turn() -> None:
    gate = MountGate()
    proceed = asyncio.Event()
    release_other = asyncio.Event()
    entered: list[str] = []

    async def late_call() -> None:
        await proceed.wait()
        async with gate.hold():
            entered.append("late")

    async def other_call() -> None:
        async with gate.hold():
            entered.append("other")
            await release_other.wait()

    async with gate.hold():
        # The task inherits the hold that is active here, which ends before the task asks for its turn.
        late = asyncio.create_task(late_call())
    other = asyncio.create_task(other_call())
    await asyncio.sleep(0)
    proceed.set()
    # A call that wrongly skipped the wait would have entered by now.
    await asyncio.sleep(0.05)
    assert entered == ["other"]

    release_other.set()
    async with asyncio.timeout(10):
        await asyncio.gather(late, other)

    assert entered == ["other", "late"]


async def test_copy_shares_the_gate_and_pickle_creates_a_fresh_one() -> None:
    gate = MountGate()

    async with gate.hold():
        assert copy.deepcopy(gate) is gate
        # The pickle carries no state, so it also works while the gate is held.
        restored = pickle.loads(pickle.dumps(gate))

    assert isinstance(restored, MountGate)
    assert restored is not gate
    async with asyncio.timeout(10):
        async with restored.hold():
            pass
