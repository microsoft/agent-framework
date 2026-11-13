# Copyright (c) Microsoft. All rights reserved.
"""Per-tool cooperative async deadlines using FunctionMiddleware.

Run this sample with Python 3.10 or later.
"""

import asyncio
import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from agent_framework import FunctionInvocationContext, FunctionMiddleware, MiddlewareFailure


@dataclass(frozen=True)
class DeadlinePolicy:
    """Timeout budget and side-effect classification for one tool."""

    seconds: float
    read_only: bool = False

    def __post_init__(self) -> None:
        if not math.isfinite(self.seconds) or self.seconds <= 0:
            raise ValueError("deadline must be a finite positive number")


class PerToolDeadlineMiddleware(FunctionMiddleware):
    """Enforce independent deadlines for configured async tools.

    Cancellation is cooperative. The middleware waits for task cleanup;
    therefore actual elapsed time may exceed the configured deadline.
    """

    def __init__(self, policies: dict[str, DeadlinePolicy]) -> None:
        self._policies = dict(policies)

    @staticmethod
    def _observe_task_completion(task: asyncio.Task[None]) -> None:
        """Retrieve exceptions from a task finishing after cancellation."""
        if not task.cancelled():
            task.exception()

    async def process(
        self,
        context: FunctionInvocationContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:
        policy = self._policies.get(context.function.name)
        if policy is None:
            await call_next()
            return

        task = asyncio.create_task(call_next())
        deadline_cancel_requested = False
        try:
            done, _ = await asyncio.wait({task}, timeout=policy.seconds)

            if done:
                # Propagates tool-raised TimeoutError and other exceptions.
                await task
                return

            # The deadline expired while the tool task was pending.
            deadline_cancel_requested = True
            task.cancel()

            # Wait for cooperative cleanup without suppressing
            # cancellation of the calling middleware task.
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                if not task.done():
                    # Caller cancellation during cleanup must propagate.
                    raise
                if not task.cancelled():
                    # A completed child may itself have raised cancellation.
                    raise
            except MiddlewareFailure:
                # Preserve fatal downstream middleware failures.
                raise
            except Exception:
                # Ordinary cleanup errors do not establish that the
                # timed-out operation completed successfully.
                pass

            if policy.read_only:
                context.result = f"Read-only tool '{context.function.name}' exceeded its deadline."
                return

            raise MiddlewareFailure(
                f"Tool '{context.function.name}' exceeded its deadline; remote side effects may have occurred."
            )

        except asyncio.CancelledError:
            # Avoid cancelling the child a second time while it is
            # already performing deadline-triggered cleanup.
            if not deadline_cancel_requested:
                task.cancel()
            task.add_done_callback(self._observe_task_completion)
            # Preserve caller cancellation. The tool may continue cleanup.
            raise


async def main() -> None:
    """Demonstrate recoverable and uncertain deadline expiry."""

    from types import SimpleNamespace

    middleware = PerToolDeadlineMiddleware({
        "lookup": DeadlinePolicy(0.01, read_only=True),
        "update": DeadlinePolicy(0.01, read_only=False),
    })

    async def slow_tool() -> None:
        await asyncio.sleep(0.05)

    for name in ("lookup", "update"):
        context = SimpleNamespace(
            function=SimpleNamespace(name=name),
            result=None,
        )
        try:
            await middleware.process(context, slow_tool)
            print(f"{name}: {context.result}")
        except MiddlewareFailure as exc:
            print(f"{name}: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
