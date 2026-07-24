# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for the persistent async bridge used by durable handlers."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Iterator
from unittest.mock import Mock

import pytest

import agent_framework_durabletask._async_bridge as async_bridge


@pytest.fixture(autouse=True)
def _restore_bridge_globals() -> Iterator[None]:
    old_loop = async_bridge._loop
    old_thread = async_bridge._thread
    old_lock = async_bridge._lock

    async_bridge._loop = None
    async_bridge._thread = None
    async_bridge._lock = threading.Lock()

    yield

    new_loop = async_bridge._loop
    new_thread = async_bridge._thread
    if new_loop is not None and not new_loop.is_closed():
        new_loop.call_soon_threadsafe(new_loop.stop)
    if new_thread is not None and new_thread.is_alive():
        new_thread.join(timeout=1)
    if new_loop is not None and not new_loop.is_closed():
        new_loop.close()

    async_bridge._loop = old_loop
    async_bridge._thread = old_thread
    async_bridge._lock = old_lock


def test_ensure_loop_reuses_existing_live_loop() -> None:
    loop = asyncio.new_event_loop()
    thread = Mock()
    thread.is_alive.return_value = True
    async_bridge._loop = loop
    async_bridge._thread = thread

    assert async_bridge._ensure_loop() is loop


def test_ensure_loop_replaces_orphaned_loop() -> None:
    orphaned_loop = asyncio.new_event_loop()
    dead_thread = Mock()
    dead_thread.is_alive.return_value = False
    async_bridge._loop = orphaned_loop
    async_bridge._thread = dead_thread

    new_loop = async_bridge._ensure_loop()

    assert new_loop is not orphaned_loop
    assert orphaned_loop.is_closed() is True
    assert async_bridge._thread is not None
    assert async_bridge._thread.is_alive() is True


def test_run_agent_coroutine_executes_on_shared_loop() -> None:
    async def _compute() -> str:
        await asyncio.sleep(0)
        return "done"

    assert async_bridge.run_agent_coroutine(_compute()) == "done"
    assert async_bridge._loop is not None
    assert async_bridge._thread is not None
