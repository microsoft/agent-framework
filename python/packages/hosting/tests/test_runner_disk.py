# Copyright (c) Microsoft. All rights reserved.

"""Tests for :class:`InProcessTaskRunner` disk persistence (``state_dir``)."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from agent_framework_hosting import (
    InProcessTaskRunner,
    PushPayloadNotPicklable,
    RetryPolicy,
)

# Skip the whole module if the optional diskcache dependency isn't installed.
pytest.importorskip("diskcache")


# --------------------------------------------------------------------------- #
# state_dir=None preserves today's purely in-memory contract                  #
# --------------------------------------------------------------------------- #


async def test_state_dir_none_is_pure_memory(tmp_path: Path) -> None:
    """No directory creation / no lock file when state_dir is omitted."""
    runner = InProcessTaskRunner()
    calls: list[Mapping[str, Any]] = []

    async def handler(payload: Mapping[str, Any]) -> None:
        calls.append(payload)

    runner.register("echo", handler)
    handle = await runner.schedule("echo", {"k": "v"})

    # Wait for completion.
    for _ in range(50):
        if (await runner.get(handle)) == "succeeded":
            break
        await asyncio.sleep(0.01)
    assert calls == [{"k": "v"}]
    assert await runner.get(handle) == "succeeded"
    # Confirm we didn't accidentally write to disk.
    assert not (tmp_path / ".lock").exists()

    await runner.shutdown()


# --------------------------------------------------------------------------- #
# Lock contention — two runners on the same dir refuse to coexist             #
# --------------------------------------------------------------------------- #


async def test_two_runners_one_state_dir_raise(tmp_path: Path) -> None:
    """Second runner construction must fail loudly, not silently corrupt."""
    state_dir = tmp_path / "runner"
    first = InProcessTaskRunner(state_dir=state_dir)
    try:
        with pytest.raises(RuntimeError, match="state lock"):
            InProcessTaskRunner(state_dir=state_dir)
    finally:
        await first.shutdown()


# --------------------------------------------------------------------------- #
# Pickle failure raises eagerly, never silently downgrades                    #
# --------------------------------------------------------------------------- #


async def test_unpickleable_payload_raises(tmp_path: Path) -> None:
    """Schedule must refuse payloads that can't survive a restart."""
    runner = InProcessTaskRunner(state_dir=tmp_path / "runner")

    async def handler(_: Mapping[str, Any]) -> None: ...

    runner.register("echo", handler)
    # Local lambdas / closures are the canonical unpicklable values.
    with pytest.raises(PushPayloadNotPicklable):
        await runner.schedule("echo", {"callback": lambda: None})
    await runner.shutdown()


# --------------------------------------------------------------------------- #
# Resume — pending records replay on next process                             #
# --------------------------------------------------------------------------- #


async def test_pending_record_replays_on_resume(tmp_path: Path) -> None:
    """Simulate a crash: first runner schedules but never starts running."""
    state_dir = tmp_path / "runner"

    # Process 1 — schedule a task, then "die" before the asyncio loop runs it.
    runner1 = InProcessTaskRunner(state_dir=state_dir)
    blocked = asyncio.Event()

    async def slow(_: Mapping[str, Any]) -> None:
        # Sleep so the task is observably still in flight when we shutdown.
        await blocked.wait()

    runner1.register("slow", slow)
    handle = await runner1.schedule("slow", {"work": 1})
    # Force a hard shutdown — leaves the in-flight task in 'pending' on disk.
    await runner1.shutdown(timeout=0.1)

    # Process 2 — fresh runner against same state_dir, register the handler,
    # call resume. We expect the persisted record to be re-scheduled.
    runner2 = InProcessTaskRunner(state_dir=state_dir)
    seen: list[Mapping[str, Any]] = []

    async def slow_resumed(payload: Mapping[str, Any]) -> None:
        seen.append(dict(payload))

    runner2.register("slow", slow_resumed)
    replayed = await runner2.resume()
    assert replayed == 1

    # Give the resumed task time to run.
    for _ in range(50):
        if seen:
            break
        await asyncio.sleep(0.01)
    assert seen == [{"work": 1}]
    # Status is observable via the original handle.
    assert await runner2.get(handle) == "succeeded"

    await runner2.shutdown()


# --------------------------------------------------------------------------- #
# echo_done cursor survives restart                                            #
# --------------------------------------------------------------------------- #


async def test_payload_mutation_survives_restart(tmp_path: Path) -> None:
    """Handler-side payload mutations (echo_done) round-trip through disk."""
    state_dir = tmp_path / "runner"
    runner1 = InProcessTaskRunner(state_dir=state_dir)

    # Handler sets echo_done and then blocks forever (simulating mid-flight crash).
    handler_progress = asyncio.Event()

    async def half_done(payload: Mapping[str, Any]) -> None:
        # Mutate the payload to mark first phase complete.
        payload["echo_done"] = True  # type: ignore[index]
        handler_progress.set()
        # Sleep indefinitely so the asyncio task is still running at shutdown.
        await asyncio.Event().wait()

    runner1.register("two_phase", half_done)
    handle = await runner1.schedule("two_phase", {"echo_done": False, "k": "v"})
    await handler_progress.wait()
    await runner1.shutdown(timeout=0.1)

    # Process 2 — replay; the handler now sees echo_done=True from disk.
    runner2 = InProcessTaskRunner(state_dir=state_dir)
    observed: list[bool] = []

    async def two_phase_resumed(payload: Mapping[str, Any]) -> None:
        observed.append(bool(payload.get("echo_done")))

    runner2.register("two_phase", two_phase_resumed)
    await runner2.resume()

    for _ in range(50):
        if observed:
            break
        await asyncio.sleep(0.01)
    assert observed == [True]
    # And the resumed task ran to completion.
    assert await runner2.get(handle) == "succeeded"

    await runner2.shutdown()


# --------------------------------------------------------------------------- #
# Resume gracefully handles missing handler / corrupt entries                  #
# --------------------------------------------------------------------------- #


async def test_resume_with_missing_handler_marks_failed(tmp_path: Path) -> None:
    """A persisted record whose handler is no longer registered is marked failed."""
    state_dir = tmp_path / "runner"

    runner1 = InProcessTaskRunner(state_dir=state_dir)

    async def will_be_removed(_: Mapping[str, Any]) -> None:
        await asyncio.Event().wait()

    runner1.register("ghost", will_be_removed)
    handle = await runner1.schedule("ghost", {})
    await runner1.shutdown(timeout=0.1)

    # Process 2 — never registers "ghost".
    runner2 = InProcessTaskRunner(state_dir=state_dir)
    replayed = await runner2.resume()
    assert replayed == 0
    # The record is moved to terminal 'failed'.
    assert await runner2.get(handle) == "failed"
    await runner2.shutdown()


async def test_resume_quarantines_corrupt_entries(tmp_path: Path) -> None:
    """A non-dict on-disk entry must be quarantined, not crash resume."""
    import diskcache  # noqa: PLC0415 - lazy import to keep module-import cheap

    state_dir = tmp_path / "runner"
    state_dir.mkdir(parents=True, exist_ok=True)
    # Pre-populate the cache with a junk entry.
    cache = diskcache.Cache(str(state_dir))
    cache.set("bad-task-id", "this is not a dict")
    cache.close()

    runner = InProcessTaskRunner(state_dir=state_dir)
    # resume() must not raise even with a corrupt entry on disk.
    replayed = await runner.resume()
    assert replayed == 0
    await runner.shutdown()

    # The corrupt entry should have been removed.
    cache2 = diskcache.Cache(str(state_dir))
    assert "bad-task-id" not in cache2
    cache2.close()


# --------------------------------------------------------------------------- #
# Retry attempt counter persists across resume                                 #
# --------------------------------------------------------------------------- #


async def test_attempt_counter_persists_across_resume(tmp_path: Path) -> None:
    """A handler that crashes mid-attempt resumes with the consumed budget."""
    state_dir = tmp_path / "runner"
    policy = RetryPolicy(max_attempts=3, initial_backoff_seconds=0.01, backoff_multiplier=1.0)

    # Process 1 — schedule, fail once, shutdown before retry settles.
    runner1 = InProcessTaskRunner(state_dir=state_dir, default_retry_policy=policy)
    attempts_seen_p1 = 0

    async def flaky(_: Mapping[str, Any]) -> None:
        nonlocal attempts_seen_p1
        attempts_seen_p1 += 1
        raise RuntimeError("boom-1")

    runner1.register("flaky", flaky)
    handle = await runner1.schedule("flaky", {})
    # Let it attempt twice (waste 2 of 3 budgeted retries), then crash-shutdown.
    for _ in range(50):
        if attempts_seen_p1 >= 2:
            break
        await asyncio.sleep(0.01)
    await runner1.shutdown(timeout=0.05)

    # Process 2 — resume; only 1 attempt left in the budget. Confirm we don't
    # re-grant the full retry budget.
    runner2 = InProcessTaskRunner(state_dir=state_dir, default_retry_policy=policy)
    attempts_seen_p2 = 0

    async def flaky_resumed(_: Mapping[str, Any]) -> None:
        nonlocal attempts_seen_p2
        attempts_seen_p2 += 1
        raise RuntimeError("boom-2")

    runner2.register("flaky", flaky_resumed)
    await runner2.resume()
    # Wait for the resumed task to consume its remaining attempts and fail terminally.
    for _ in range(100):
        if (await runner2.get(handle)) == "failed":
            break
        await asyncio.sleep(0.01)
    assert await runner2.get(handle) == "failed"
    # Original consumed 2 attempts; we should have allowed at most max_attempts-2=1
    # more in process 2.
    assert attempts_seen_p2 <= 1
    await runner2.shutdown()
