# Copyright (c) Microsoft. All rights reserved.

"""AsyncRequestBroker: a generic asyncio pause-and-wait primitive.

Provides :class:`AsyncRequestBroker`, which lets any server-side code suspend
execution on a request ID and wait asynchronously for a client to deliver the
matching result via :meth:`AsyncRequestBroker.resolve` or
:meth:`AsyncRequestBroker.reject`.

The broker tracks recently settled request IDs in a bounded deque (default
256 entries) so that re-using a settled ID is reported instead of silently
hanging. Late responses for unknown IDs return ``False`` rather than raising.

Usage::

    broker = AsyncRequestBroker()

    # Server side - suspend until answered (or timeout)
    result = await broker.request_async("req-123", timeout=30.0)

    # Client side - deliver the answer
    broker.resolve("req-123", decision)
"""

from __future__ import annotations

import asyncio
import collections
from typing import Generic, TypeVar

from .._feature_stage import ExperimentalFeature, experimental

__all__ = ["AsyncRequestBroker"]

T = TypeVar("T")


@experimental(feature_id=ExperimentalFeature.HARNESS)
class AsyncRequestBroker(Generic[T]):
    """Generic asyncio pause-and-wait broker for request/response patterns.

    Allows server-side code to suspend on a request ID and await a client
    response delivered via :meth:`resolve` or :meth:`reject`, without
    polling or blocking a thread.

    Thread-safety: designed for single-threaded asyncio use. The broker must
    be used within a single event loop.
    """

    DEFAULT_SETTLED_DEQUE_SIZE = 256

    def __init__(self, settled_deque_size: int = DEFAULT_SETTLED_DEQUE_SIZE) -> None:
        self._pending: dict[str, asyncio.Future[T]] = {}
        self._settled: collections.deque[str] = collections.deque(maxlen=settled_deque_size)

    async def request_async(self, request_id: str, *, timeout: float | None = None) -> T:
        """Suspend until the request is resolved or rejected.

        Args:
            request_id: Unique identifier for this request.

        Keyword Args:
            timeout: Maximum seconds to wait. ``None`` waits indefinitely.

        Returns:
            The result passed to :meth:`resolve`.

        Raises:
            ValueError: If the ID is already pending or was recently settled.
            asyncio.TimeoutError: If ``timeout`` elapses before a response arrives.
            asyncio.CancelledError: If the waiting task is cancelled.
            Exception: Any exception passed to :meth:`reject`.
        """
        if request_id in self._settled:
            raise ValueError(f"Request '{request_id}' was already settled.")
        if request_id in self._pending:
            raise ValueError(f"Request '{request_id}' is already pending.")
        loop = asyncio.get_running_loop()
        future: asyncio.Future[T] = loop.create_future()
        self._pending[request_id] = future
        try:
            return await asyncio.wait_for(asyncio.shield(future), timeout=timeout)
        except BaseException:
            if self._pending.get(request_id) is future:
                del self._pending[request_id]
            future.cancel()
            raise

    def resolve(self, request_id: str, result: T) -> bool:
        """Deliver a successful result to a waiting :meth:`request_async` call.

        Returns:
            ``True`` if a waiter was notified, ``False`` if the request was not found
            (already settled or never registered).
        """
        future = self._pending.pop(request_id, None)
        if future is None:
            return False
        self._settled.append(request_id)
        if not future.done():
            future.set_result(result)
        return True

    def reject(self, request_id: str, exception: BaseException) -> bool:
        """Deliver an exception to a waiting :meth:`request_async` call.

        Returns:
            ``True`` if a waiter was notified.
        """
        future = self._pending.pop(request_id, None)
        if future is None:
            return False
        self._settled.append(request_id)
        if not future.done():
            future.set_exception(exception)
        return True

    @property
    def pending_count(self) -> int:
        """Number of outstanding requests currently awaiting a response."""
        return len(self._pending)
