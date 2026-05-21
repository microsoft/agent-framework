# Copyright (c) Microsoft. All rights reserved.

"""In-process implementation of :class:`DurableTaskRunner`.

This is the default runner the host wires in when the operator does not
supply one. It runs tasks via :func:`asyncio.create_task` with a bounded
retry loop following the supplied :class:`RetryPolicy`. **No persistence**
— in-flight tasks are lost on process death. Suitable for
``runtime_mode="long_running"`` deployments (always-on container, owns its
own scheduler) where "the process dies, queued pushes are lost" is an
acceptable failure mode. For ``runtime_mode="ephemeral"`` deployments
(Foundry Hosted Agent, Azure Functions, Lambda) plug in a durable adapter
package (``agent-framework-hosting-durabletask`` for the gRPC TaskHub
backend, a future Foundry adapter, …) — they all implement the same
:class:`DurableTaskRunner` Protocol.

See ``docs/specs/002-python-hosting-channels.md`` § "Durable task runner".
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from ._types import DurableTaskPayloadMode, DurableTaskRunner, RetryPolicy, TaskHandle, TaskStatus

logger = logging.getLogger(__name__)


class InProcessTaskRunner(DurableTaskRunner):
    """In-memory :class:`DurableTaskRunner` that retries via ``asyncio.sleep``.

    Designed for ``runtime_mode="long_running"`` deployments. Schedules each
    task as an :func:`asyncio.create_task` coroutine and retries on
    exception up to ``RetryPolicy.max_attempts`` times with exponential
    backoff. Records terminal status (``succeeded`` / ``failed`` /
    ``cancelled``) in a bounded in-memory cache so :meth:`get` can report
    it back; the cache is purged on a TTL to bound memory.

    Re-registration of the same handler name after :meth:`schedule` has been
    called is rejected to avoid silent re-orderings of in-flight work; the
    host registers all handlers at startup, before serving traffic.
    """

    # Declared at class level so the ``DurableTaskRunner`` Protocol's
    # ``payload_mode`` attribute resolves on instances without needing
    # to assign it in ``__init__``.
    payload_mode: DurableTaskPayloadMode = DurableTaskPayloadMode.OBJECT

    def __init__(
        self,
        *,
        default_retry_policy: RetryPolicy | None = None,
        terminal_cache_size: int = 1024,
        shutdown_grace_seconds: float = 5.0,
    ) -> None:
        self._handlers: dict[str, Callable[[Mapping[str, Any]], Awaitable[None]]] = {}
        self._default_retry_policy = default_retry_policy or RetryPolicy()
        self._terminal_cache_size = terminal_cache_size
        # How long ``shutdown()`` waits for in-flight tasks to finish on
        # their own before cancelling them. Channels may legitimately
        # schedule a final push during their own shutdown callback
        # (goodbye message, telemetry flush), so the runner gives them
        # this window to complete before cancellation kicks in.
        self._shutdown_grace_seconds = shutdown_grace_seconds

        # Operational state. ``_pending`` holds tasks that are scheduled or
        # running; ``_terminal`` is a bounded ring of final outcomes. The
        # ring is FIFO-bounded (oldest entry dropped) so the runner can't
        # leak memory under sustained schedule rates.
        self._pending: dict[str, asyncio.Task[None]] = {}
        self._terminal: dict[str, TaskStatus] = {}
        self._terminal_order: list[str] = []

        # Set to True on the first ``schedule`` call so subsequent
        # ``register`` calls fail loudly rather than silently swapping a
        # handler out from under in-flight work.
        self._started = False

    # ------------------------------------------------------------------ #
    # DurableTaskRunner Protocol
    # ------------------------------------------------------------------ #

    def register(
        self,
        name: str,
        handler: Callable[[Mapping[str, Any]], Awaitable[None]],
    ) -> None:
        if self._started:
            raise RuntimeError(
                f"InProcessTaskRunner.register({name!r}) called after the "
                "runner started scheduling tasks — register all handlers at "
                "host startup, before serving traffic, to avoid silently "
                "reordering in-flight work."
            )
        if name in self._handlers:
            logger.warning("InProcessTaskRunner: replacing handler registered under %r", name)
        self._handlers[name] = handler

    async def schedule(
        self,
        name: str,
        payload: Mapping[str, Any],
        *,
        retry_policy: RetryPolicy | None = None,
    ) -> TaskHandle:
        if name not in self._handlers:
            raise KeyError(
                f"InProcessTaskRunner.schedule({name!r}): no handler "
                "registered under this name. Call register(name, handler) "
                "at host startup before scheduling."
            )

        self._started = True
        policy = retry_policy or self._default_retry_policy
        task_id = uuid.uuid4().hex
        handle = TaskHandle(task_id=task_id, name=name)

        # Capture handler + payload now — re-registration is rejected after
        # ``_started`` flips, so this is the definitive reference.
        handler = self._handlers[name]
        task = asyncio.create_task(
            self._run_with_retry(handle, handler, payload, policy),
            name=f"hosting.task[{name}]:{task_id}",
        )
        self._pending[task_id] = task
        # Drop self-reference from ``_pending`` when the task finishes,
        # whether it succeeded or failed. The terminal status is recorded
        # inside ``_run_with_retry`` before the coroutine returns.

        def _on_done(_t: asyncio.Task[None], tid: str = task_id) -> None:
            self._pending.pop(tid, None)

        task.add_done_callback(_on_done)
        return handle

    async def get(self, handle: TaskHandle) -> TaskStatus | None:
        if handle.task_id in self._pending:
            task = self._pending[handle.task_id]
            if task.cancelled():
                return "cancelled"
            return "running"
        return self._terminal.get(handle.task_id)

    # ------------------------------------------------------------------ #
    # Lifecycle helper (the host calls this from ``on_shutdown``)
    # ------------------------------------------------------------------ #

    async def shutdown(self, *, timeout: float | None = None) -> None:
        """Wait briefly for pending tasks to drain, then cancel anything still running.

        Called by the host on ``on_shutdown`` so a graceful shutdown does
        not orphan in-flight push retries. Channels may legitimately
        schedule a final push from their own shutdown callback (e.g. a
        goodbye message); the runner therefore *waits* up to
        ``timeout`` seconds (default: the runner's
        ``shutdown_grace_seconds`` configured at construction) for the
        in-flight set to finish on its own before cancelling stragglers.
        Tasks that don't honour cancellation within the same window are
        abandoned — the in-process runner makes no durability claim, so
        cleanup is best-effort by design.
        """
        if not self._pending:
            return
        grace = timeout if timeout is not None else self._shutdown_grace_seconds
        tasks = list(self._pending.values())
        # Phase 1 — wait for natural completion within the grace window.
        # ``asyncio.wait`` does not raise on timeout (it just returns the
        # split sets), which is what we want: the loser tasks roll over
        # into the cancellation phase.
        if grace > 0:
            await asyncio.wait(tasks, timeout=grace)
        # Phase 2 — cancel anything still pending, then wait briefly for
        # cancellation to propagate. Tasks that ignore cancellation
        # within the cancellation window are logged and abandoned.
        still_pending = [t for t in tasks if not t.done()]
        if not still_pending:
            return
        logger.info(
            "InProcessTaskRunner.shutdown: %d task(s) still running after %.2fs grace; cancelling",
            len(still_pending),
            grace,
        )
        for task in still_pending:
            task.cancel()
        cancellation_window = max(grace, 1.0)
        try:
            await asyncio.wait_for(
                asyncio.gather(*still_pending, return_exceptions=True),
                timeout=cancellation_window,
            )
        except (TimeoutError, asyncio.TimeoutError):
            logger.warning(
                "InProcessTaskRunner.shutdown: %d task(s) did not exit within %.2fs of cancellation; abandoning",
                sum(not t.done() for t in still_pending),
                cancellation_window,
            )

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    async def _run_with_retry(
        self,
        handle: TaskHandle,
        handler: Callable[[Mapping[str, Any]], Awaitable[None]],
        payload: Mapping[str, Any],
        policy: RetryPolicy,
    ) -> None:
        delay = policy.initial_backoff_seconds
        attempt = 0
        try:
            while True:
                attempt += 1
                try:
                    await handler(payload)
                except asyncio.CancelledError:
                    # Honour cancellation immediately — the runner is being
                    # shut down. Record terminal state so a late ``get``
                    # call can still see the outcome.
                    self._record_terminal(handle.task_id, "cancelled")
                    raise
                except Exception as exc:
                    if attempt >= policy.max_attempts:
                        logger.exception(
                            "InProcessTaskRunner: task %s (%s) failed after %d attempts",
                            handle.name,
                            handle.task_id,
                            attempt,
                        )
                        self._record_terminal(handle.task_id, "failed")
                        return
                    logger.warning(
                        "InProcessTaskRunner: task %s (%s) attempt %d/%d failed (%s); retrying in %.2fs",
                        handle.name,
                        handle.task_id,
                        attempt,
                        policy.max_attempts,
                        exc,
                        delay,
                    )
                    try:
                        await asyncio.sleep(delay)
                    except asyncio.CancelledError:
                        self._record_terminal(handle.task_id, "cancelled")
                        raise
                    delay = min(delay * policy.backoff_multiplier, policy.max_backoff_seconds)
                else:
                    self._record_terminal(handle.task_id, "succeeded")
                    return
        except asyncio.CancelledError:
            # Propagate so the outer ``asyncio.Task`` records cancellation
            # in its own state for any observer that holds the raw task.
            return

    def _record_terminal(self, task_id: str, status: TaskStatus) -> None:
        # Bounded FIFO so a long-running host can't accumulate unbounded
        # terminal-status entries. ``get`` callers that care about a stale
        # task id get ``None`` once it ages out — same contract as a
        # process restart, which is consistent with this runner's
        # no-cross-restart-persistence stance.
        if task_id in self._terminal:
            self._terminal[task_id] = status
            return
        self._terminal[task_id] = status
        self._terminal_order.append(task_id)
        while len(self._terminal_order) > self._terminal_cache_size:
            evicted = self._terminal_order.pop(0)
            self._terminal.pop(evicted, None)


__all__ = ["InProcessTaskRunner"]
