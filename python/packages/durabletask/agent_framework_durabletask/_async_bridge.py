# Copyright (c) Microsoft. All rights reserved.

"""Persistent background event loop for running agent coroutines.

Durable entity (and agent) handlers are invoked synchronously by the host on
arbitrary worker threads. Agent clients and their async credentials create
asyncio primitives (locks, connection pools, futures) that are bound to the
event loop on which they are *first* used. Running a later invocation on a
*different* event loop causes those primitives to await futures attached to a
now-idle loop, which results in a silent, permanent hang.

This module provides a single, process-wide persistent event loop running on a
dedicated daemon thread. All agent coroutines are submitted to this loop via
``run_coroutine_threadsafe`` so shared async resources remain valid across
invocations regardless of which worker thread the host happens to use.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from typing import Any, TypeVar

_T = TypeVar("_T")

_loop: asyncio.AbstractEventLoop | None = None
_thread: threading.Thread | None = None
_lock = threading.Lock()


def _ensure_loop() -> asyncio.AbstractEventLoop:
    """Return the shared persistent event loop, starting it on first use."""
    global _loop, _thread

    if _loop is not None and not _loop.is_closed():
        return _loop

    with _lock:
        if _loop is not None and not _loop.is_closed():
            return _loop

        loop = asyncio.new_event_loop()

        def _run() -> None:
            asyncio.set_event_loop(loop)
            loop.run_forever()

        thread = threading.Thread(target=_run, name="dafx-agent-loop", daemon=True)
        thread.start()

        _loop = loop
        _thread = thread
        return loop


def run_agent_coroutine(coro: Coroutine[Any, Any, _T]) -> _T:
    """Run a coroutine on the shared persistent event loop and return its result.

    The calling (worker) thread blocks until the coroutine completes. Because
    every agent coroutine runs on the same loop, async resources created by
    shared agent clients/credentials (locks, connection pools) remain bound to a
    live loop across all invocations, preventing cross-loop hangs.

    Args:
        coro: The coroutine to execute.

    Returns:
        The coroutine's result.
    """
    loop = _ensure_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result()
