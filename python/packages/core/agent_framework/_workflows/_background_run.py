# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from ._events import WorkflowEvent
from ._runner_context import RunnerContext

logger = logging.getLogger(__name__)


class BackgroundRunHandle:
    """Handle for a workflow running in the background.

    Provides a polling interface to consume events produced by a background
    workflow execution. The workflow runs in an ``asyncio.Task`` and events
    are buffered in an internal queue until the caller drains them via
    :meth:`poll`.

    Responses to ``request_info`` events can be sent while the workflow is
    still running via :meth:`respond`, enabling hot-path / cold-path
    parallelism.

    Example:
        .. code-block:: python

            handle = workflow.run_in_background(message="Hello")
            while not handle.is_idle:
                events = await handle.poll()
                for event in events:
                    if event.type == "request_info":
                        await handle.respond({event.request_id: answer})
    """

    def __init__(
        self,
        task: asyncio.Task[None],
        event_queue: asyncio.Queue[WorkflowEvent[Any]],
        runner_context: RunnerContext,
        resume_fn: Callable[[], Awaitable[asyncio.Task[None]]],
    ) -> None:
        """Initialize the background run handle.

        Args:
            task: The asyncio task running the workflow.
            event_queue: The queue where workflow events are buffered.
            runner_context: The runner context for injecting responses.
            resume_fn: Callback that creates and returns a new producer task
                to resume the workflow after it has converged.
        """
        self._task = task
        self._event_queue = event_queue
        self._runner_context = runner_context
        self._resume_fn = resume_fn

    @property
    def is_idle(self) -> bool:
        """Whether the background task has finished producing events.

        This becomes ``True`` when the background task completes, which happens
        when the workflow reaches any terminal run state — including
        :attr:`~WorkflowRunState.IDLE`,
        :attr:`~WorkflowRunState.IDLE_WITH_PENDING_REQUESTS`, or
        :attr:`~WorkflowRunState.FAILED`. To determine which state the workflow
        ended in, inspect the status events returned by :meth:`poll`.
        """
        return self._task.done()

    async def poll(self) -> list[WorkflowEvent[Any]]:
        """Drain all currently queued events without blocking.

        Returns:
            A list of events produced since the last poll. Returns an empty
            list if no events are available.
        """
        events: list[WorkflowEvent[Any]] = []
        # Use get_nowait() in a loop to drain all available events.
        # This is safe from race conditions because asyncio uses cooperative
        # multitasking: since we never await inside this loop, no other
        # coroutine (including the background task producing events) can
        # execute until we finish. This guarantees we get a consistent
        # snapshot of all events queued at the moment poll() was called.
        while True:
            try:
                events.append(self._event_queue.get_nowait())
            except asyncio.QueueEmpty:
                # Queue is empty — we've drained all currently available events.
                # Any events added after this point will be picked up in the
                # next poll() call.
                break
        return events

    async def respond(self, responses: dict[str, Any]) -> None:
        """Send responses to pending ``request_info`` events.

        If the workflow is still running, the responses are injected into the
        runner context and picked up in the next superstep. If the workflow
        has already converged (idle), the responses are injected and the
        runner is automatically resumed.

        Args:
            responses: A mapping of request IDs to response data.

        Raises:
            ValueError: If a request ID is unknown.
            TypeError: If a response type does not match the expected type.
        """
        for request_id, response in responses.items():
            await self._runner_context.send_request_info_response(request_id, response)

        if self.is_idle:
            self._task = await self._resume_fn()
