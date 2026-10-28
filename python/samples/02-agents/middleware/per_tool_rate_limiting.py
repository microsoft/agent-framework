# Copyright (c) Microsoft. All rights reserved.
"""Local per-tool token-bucket admission control using FunctionMiddleware.

A quota belongs to this middleware instance and is keyed by the tool name.
It is not a distributed limit and it does not make tool execution idempotent.
A rejected invocation returns a tool-visible result without invoking the tool.
"""

import asyncio
import math
import threading
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from agent_framework import FunctionInvocationContext, FunctionMiddleware


@dataclass(frozen=True)
class RatePolicy:
    capacity: int
    refill_per_second: float

    def __post_init__(self) -> None:
        if (
            isinstance(self.capacity, bool)
            or not isinstance(self.capacity, int)
            or self.capacity <= 0
            or not math.isfinite(self.refill_per_second)
            or self.refill_per_second <= 0
        ):
            raise ValueError("capacity and refill_per_second must be finite and positive")


class PerToolRateLimitMiddleware(FunctionMiddleware):
    """Share one quota per tool name across concurrent calls and event loops."""

    def __init__(self, policies: Mapping[str, RatePolicy]) -> None:
        self._policies = dict(policies)
        self._buckets: dict[str, tuple[float, float]] = {}
        # No asyncio primitives: one instance can be reused across event loops.
        self._lock = threading.Lock()

    def admit(self, name: str, *, now: float | None = None) -> bool:
        """Atomically spend one token, or reject without spending a token."""
        policy = self._policies.get(name)
        if policy is None:
            return True
        timestamp = time.monotonic() if now is None else now
        with self._lock:
            tokens, last = self._buckets.get(name, (float(policy.capacity), timestamp))
            elapsed = max(0.0, timestamp - last)
            tokens = min(float(policy.capacity), tokens + elapsed * policy.refill_per_second)
            admitted = tokens >= 1.0
            self._buckets[name] = (tokens - 1.0 if admitted else tokens, max(last, timestamp))
            return admitted

    async def process(self, context: FunctionInvocationContext, call_next: Callable[[], Awaitable[None]]) -> None:
        name = context.function.name
        if not self.admit(name):
            # Do not use MiddlewareTermination: it can terminate the tool loop.
            context.result = f"Tool '{name}' is rate limited. Retry later if appropriate."
            return
        # Never hold the lock during execution. Do not swallow cancellation.
        await call_next()


async def main() -> None:
    limiter = PerToolRateLimitMiddleware({"lookup": RatePolicy(2, 0.01)})
    for _ in range(3):
        context: Any = SimpleNamespace(function=SimpleNamespace(name="lookup"), result=None)

        async def invoke(current: Any = context) -> None:
            current.result = "tool executed"

        await limiter.process(context, invoke)
        print(context.result)


if __name__ == "__main__":
    asyncio.run(main())
