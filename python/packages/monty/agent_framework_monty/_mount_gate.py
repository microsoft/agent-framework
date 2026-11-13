# Copyright (c) Microsoft. All rights reserved.

"""Lets ``execute_code`` calls that can write to the same host files take turns."""

from __future__ import annotations

import asyncio
import collections
import contextlib
import threading
from collections.abc import AsyncGenerator
from contextvars import ContextVar
from typing import Any

#: How long a call waits for its turn before it fails, in seconds.
WAIT_TIMEOUT_SECS = 600.0


class MountGateTimeoutError(TimeoutError):
    """Raised when a call waits too long for its turn."""


class _Hold:
    """One turn: the call that has it, plus the calls started inside it that are still running."""

    __slots__ = ("calls", "gate")

    def __init__(self, gate: MountGate) -> None:
        self.gate = gate
        self.calls = 1


_HELD: ContextVar[tuple[_Hold, ...]] = ContextVar("agent_framework_monty_held_mount_gates", default=())


def _grant(waiter: asyncio.Future[None]) -> None:
    if not waiter.done():
        waiter.set_result(None)


def _expire(waiter: asyncio.Future[None], timeout: float) -> None:
    if not waiter.done():
        waiter.set_exception(
            MountGateTimeoutError(
                f"Timed out after {timeout:g} seconds waiting for another execute_code call "
                "that uses the same writable mount."
            )
        )


class MountGate:
    """Serializes calls that can write to the same host files.

    Waiting calls are served in arrival order. The gate works across event loops and threads. A call that a host
    tool makes while its own call holds the gate (for example a sub-agent that uses the same provider) is part of
    that call's turn, so it does not wait. The turn lasts until the call and every call started inside it have
    ended, even when a host tool leaves one running in the background.
    """

    def __init__(self) -> None:
        self._state = threading.Lock()
        self._held = False
        self._waiters: collections.deque[tuple[asyncio.AbstractEventLoop, asyncio.Future[None]]] = collections.deque()

    def __deepcopy__(self, memo: dict[int, Any]) -> MountGate:
        # A copy of a tool uses the same host files, so it takes turns with the original.
        return self

    def __reduce__(self) -> tuple[type[MountGate], tuple[()]]:
        # The queue holds event-loop objects that cannot be pickled, so an unpickled tool starts with a fresh gate.
        return (MountGate, ())

    @contextlib.asynccontextmanager
    async def hold(self) -> AsyncGenerator[None]:
        """Wait for a turn and keep it until the block and every call started inside it have ended."""
        entry = self._join_turn()
        token = None
        if entry is None:
            await self._acquire()
            entry = _Hold(self)
            token = _HELD.set((*_HELD.get(), entry))
        try:
            yield
        finally:
            if token is not None:
                _HELD.reset(token)
            with self._state:
                entry.calls -= 1
                last = entry.calls == 0
            if last:
                self._release()

    def _join_turn(self) -> _Hold | None:
        # A call that a running call started belongs to that call's turn. A turn whose calls have all ended is over.
        with self._state:
            for entry in reversed(_HELD.get()):
                if entry.gate is self and entry.calls:
                    entry.calls += 1
                    return entry
        return None

    async def _acquire(self) -> None:
        loop = asyncio.get_running_loop()
        with self._state:
            # While the gate is free nobody is queued, because a release hands the turn directly to the next waiter.
            if not self._held:
                self._held = True
                return
            waiter: asyncio.Future[None] = loop.create_future()
            entry = (loop, waiter)
            self._waiters.append(entry)
        timeout = WAIT_TIMEOUT_SECS
        timer = loop.call_later(timeout, _expire, waiter, timeout)
        try:
            await waiter
        except BaseException:
            with self._state:
                handed_over = entry not in self._waiters
                if not handed_over:
                    self._waiters.remove(entry)
            if handed_over:
                # A release already gave this call the turn, so pass it on instead of losing it.
                self._release()
            raise
        finally:
            timer.cancel()

    def _release(self) -> None:
        with self._state:
            while self._waiters:
                loop, waiter = self._waiters.popleft()
                try:
                    loop.call_soon_threadsafe(_grant, waiter)
                except RuntimeError:
                    # That loop is closed, so its waiter is gone.
                    continue
                return
            self._held = False
