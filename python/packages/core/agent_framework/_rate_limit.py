# Copyright (c) Microsoft. All rights reserved.

"""Opt-in, per-tool token-bucket admission control for function middleware."""

import asyncio
import math
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field

from ._middleware import FunctionInvocationContext, FunctionMiddleware


@dataclass(frozen=True, slots=True)
class ToolRateLimit:
    """Maximum average requests per second and available burst tokens."""

    requests_per_second: float
    burst: int = 1

    def __post_init__(self) -> None:
        if isinstance(self.requests_per_second, bool):
            raise ValueError("requests_per_second must be finite and positive")
        if not math.isfinite(self.requests_per_second) or self.requests_per_second <= 0:
            raise ValueError("requests_per_second must be finite and positive")
        if isinstance(self.burst, bool) or not isinstance(self.burst, int) or self.burst < 1:
            raise ValueError("burst must be a positive integer")


@dataclass(slots=True)
class _Bucket:
    tokens: float
    updated_at: float
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class ToolRateLimitMiddleware(FunctionMiddleware):
    """Apply instance-local, fail-fast token-bucket limits to named tools.

    Each configured tool has its own bucket. The initial bucket is full.
    Rejected calls do not execute the tool, sleep, or retry.

    Limits are local to this middleware instance and are not shared across
    processes, replicas, or distributed workers. Configure a shared external
    rate limiter when deployment-wide quotas are required.
    """

    def __init__(
        self,
        limits: Mapping[str, ToolRateLimit],
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._limits = dict(limits)
        if any(not isinstance(name, str) or not name for name in self._limits):
            raise ValueError("tool names must be non-empty strings")
        if any(not isinstance(limit, ToolRateLimit) for limit in self._limits.values()):
            raise TypeError("limits must contain ToolRateLimit values")
        self._clock = clock
        self._buckets: dict[str, _Bucket] = {}

        # Initialize buckets eagerly so concurrent calls never race to create one.
        for name, limit in self._limits.items():
            self._buckets[name] = _Bucket(
                tokens=float(limit.burst),
                updated_at=self._clock(),
            )

    async def process(
        self,
        context: FunctionInvocationContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:
        name = context.function.name
        limit = self._limits.get(name)

        if limit is None:
            await call_next()
            return

        bucket = self._buckets[name]

        async with bucket.lock:
            now = self._clock()
            elapsed = max(0.0, now - bucket.updated_at)
            bucket.tokens = min(
                float(limit.burst),
                bucket.tokens + elapsed * limit.requests_per_second,
            )
            bucket.updated_at = max(bucket.updated_at, now)

            if bucket.tokens < 1.0:
                context.result = f"Tool rate limit exceeded for '{name}'; request rejected before execution."
                return

            bucket.tokens -= 1.0

        await call_next()
