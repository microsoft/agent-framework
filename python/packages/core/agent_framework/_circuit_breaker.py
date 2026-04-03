# Copyright (c) Microsoft. All rights reserved.

"""Circuit breaker and token budget middleware for chat client resilience.

This module provides two composable ``ChatMiddleware`` implementations:

- :class:`TokenBudgetMiddleware` enforces hard caps on cumulative token usage
  and estimated cost across LLM calls, preventing runaway spend in autonomous
  agent loops.

- :class:`CircuitBreakerMiddleware` implements the standard Closed → Open →
  Half-Open state machine, protecting against cascading failures when an LLM
  provider experiences transient errors.

Both middleware are designed to be used independently or together.  When
composed, register the circuit breaker **before** the token budget middleware
so that provider failures are caught before budget accounting runs.

Examples:

    .. code-block:: python

        from agent_framework import (
            Agent,
            CircuitBreakerMiddleware,
            TokenBudgetMiddleware,
        )

        breaker = CircuitBreakerMiddleware(failure_threshold=3)
        budget = TokenBudgetMiddleware(max_total_tokens=50_000)

        agent = Agent(
            client=client,
            middleware=[breaker, budget],
        )
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from enum import Enum

from ._middleware import ChatContext, ChatMiddleware
from ._types import ChatResponse, UsageDetails, add_usage_details
from .exceptions import CircuitBreakerOpenException, TokenBudgetExceededException

logger = logging.getLogger("agent_framework")


class CircuitBreakerState(str, Enum):
    """State of the circuit breaker.

    Attributes:
        CLOSED: Normal operation — requests pass through.
        OPEN: Failures exceeded threshold — requests are blocked.
        HALF_OPEN: Probing after reset timeout — a limited number of
            requests are allowed through to test recovery.
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


# ---------------------------------------------------------------------------
# TokenBudgetMiddleware
# ---------------------------------------------------------------------------


class TokenBudgetMiddleware(ChatMiddleware):
    """Chat middleware that enforces a hard token budget across LLM calls.

    Tracks cumulative token usage and raises
    :exc:`~agent_framework.exceptions.TokenBudgetExceededException` when
    the configured limit is breached.  Works with both streaming and
    non-streaming calls.

    The middleware instance is stateful — it accumulates usage across
    multiple calls.  If registered at the agent level, it tracks the
    entire agent lifetime.  Call :meth:`reset` or create a new instance
    to start a fresh budget.

    Args:
        max_total_tokens: Maximum total tokens allowed across all calls.
        max_input_tokens: Maximum input tokens allowed (independent limit).
        max_output_tokens: Maximum output tokens allowed (independent limit).
        cost_per_input_token: Cost per input token for estimated-cost
            budgeting.
        cost_per_output_token: Cost per output token for estimated-cost
            budgeting.
        max_estimated_cost: Maximum estimated cost allowed.  Requires at
            least one of ``cost_per_input_token`` or ``cost_per_output_token``.
        warning_threshold: Fraction of any configured limit at which a
            warning is logged (default ``0.8``).  Set to ``1.0`` to disable
            warnings.

    Raises:
        ValueError: If no limits are configured, or if ``max_estimated_cost``
            is set without any ``cost_per_*_token`` rate.

    Examples:

        .. code-block:: python

            from agent_framework import Agent, TokenBudgetMiddleware

            budget = TokenBudgetMiddleware(max_total_tokens=10_000)
            agent = Agent(client=client, middleware=[budget])

            try:
                result = await agent.run("Tell me a long story")
            except TokenBudgetExceededException as exc:
                print(f"Used {exc.used} of {exc.budget} tokens")
    """

    def __init__(
        self,
        *,
        max_total_tokens: int | None = None,
        max_input_tokens: int | None = None,
        max_output_tokens: int | None = None,
        cost_per_input_token: float | None = None,
        cost_per_output_token: float | None = None,
        max_estimated_cost: float | None = None,
        warning_threshold: float = 0.8,
    ) -> None:
        has_token_limit = any(limit is not None for limit in (max_total_tokens, max_input_tokens, max_output_tokens))
        has_cost_limit = max_estimated_cost is not None

        if not has_token_limit and not has_cost_limit:
            raise ValueError(
                "At least one limit must be configured: "
                "max_total_tokens, max_input_tokens, max_output_tokens, or max_estimated_cost."
            )

        if has_cost_limit and cost_per_input_token is None and cost_per_output_token is None:
            raise ValueError(
                "max_estimated_cost requires at least one of cost_per_input_token or cost_per_output_token."
            )

        self._max_total_tokens = max_total_tokens
        self._max_input_tokens = max_input_tokens
        self._max_output_tokens = max_output_tokens
        self._cost_per_input_token = cost_per_input_token or 0.0
        self._cost_per_output_token = cost_per_output_token or 0.0
        self._max_estimated_cost = max_estimated_cost
        self._warning_threshold = warning_threshold

        self._accumulated: UsageDetails = UsageDetails()
        self._lock = asyncio.Lock()
        self._warnings_emitted: set[str] = set()

    # -- Public properties ---------------------------------------------------

    @property
    def total_tokens_used(self) -> int:
        """Total tokens consumed so far."""
        return self._accumulated.get("total_token_count") or 0

    @property
    def input_tokens_used(self) -> int:
        """Input tokens consumed so far."""
        return self._accumulated.get("input_token_count") or 0

    @property
    def output_tokens_used(self) -> int:
        """Output tokens consumed so far."""
        return self._accumulated.get("output_token_count") or 0

    @property
    def estimated_cost(self) -> float:
        """Estimated cost based on configured rates and accumulated usage."""
        return (
            self.input_tokens_used * self._cost_per_input_token + self.output_tokens_used * self._cost_per_output_token
        )

    # -- Public methods ------------------------------------------------------

    async def reset(self) -> None:
        """Reset all accumulated usage counters to zero."""
        async with self._lock:
            self._accumulated = UsageDetails()
            self._warnings_emitted.clear()
            logger.info("TokenBudgetMiddleware: budget counters reset.")

    # -- ChatMiddleware implementation ---------------------------------------

    async def process(
        self,
        context: ChatContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:
        """Enforce token budget before and after each LLM call.

        Args:
            context: Chat invocation context.
            call_next: Callable to pass control to the next middleware.

        Raises:
            TokenBudgetExceededException: When any configured limit is
                exceeded.
        """
        # Pre-call check: reject immediately if already over budget.
        self._check_limits()

        if context.stream:
            await self._process_streaming(context, call_next)
        else:
            await self._process_non_streaming(context, call_next)

    # -- Internal helpers ----------------------------------------------------

    async def _process_non_streaming(
        self,
        context: ChatContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:
        """Handle non-streaming calls."""
        await call_next()

        if isinstance(context.result, ChatResponse) and context.result.usage_details:
            await self._accumulate(context.result.usage_details)
            self._check_warnings()
            self._check_limits()
        elif isinstance(context.result, ChatResponse):
            logger.debug("TokenBudgetMiddleware: no usage_details in response; budget not updated.")

    async def _process_streaming(
        self,
        context: ChatContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:
        """Handle streaming calls via result hooks."""

        async def _on_stream_result(result: ChatResponse) -> ChatResponse:
            if result.usage_details:
                await self._accumulate(result.usage_details)
                self._check_warnings()
                self._check_limits()
            else:
                logger.debug("TokenBudgetMiddleware: no usage_details in streamed response; budget not updated.")
            return result

        context.stream_result_hooks.append(_on_stream_result)
        await call_next()

    async def _accumulate(self, usage: UsageDetails) -> None:
        """Add usage to the running total (lock-protected)."""
        async with self._lock:
            self._accumulated = add_usage_details(self._accumulated, usage)

    def _check_limits(self) -> None:
        """Raise ``TokenBudgetExceededException`` if any limit is breached."""
        if self._max_total_tokens is not None and self.total_tokens_used > self._max_total_tokens:
            raise TokenBudgetExceededException(
                f"Total token budget exceeded: {self.total_tokens_used} / {self._max_total_tokens}.",
                budget=self._max_total_tokens,
                used=self.total_tokens_used,
            )

        if self._max_input_tokens is not None and self.input_tokens_used > self._max_input_tokens:
            raise TokenBudgetExceededException(
                f"Input token budget exceeded: {self.input_tokens_used} / {self._max_input_tokens}.",
                budget=self._max_input_tokens,
                used=self.input_tokens_used,
            )

        if self._max_output_tokens is not None and self.output_tokens_used > self._max_output_tokens:
            raise TokenBudgetExceededException(
                f"Output token budget exceeded: {self.output_tokens_used} / {self._max_output_tokens}.",
                budget=self._max_output_tokens,
                used=self.output_tokens_used,
            )

        if self._max_estimated_cost is not None and self.estimated_cost > self._max_estimated_cost:
            raise TokenBudgetExceededException(
                f"Estimated cost budget exceeded: {self.estimated_cost:.6f} / {self._max_estimated_cost:.6f}.",
                budget=self._max_estimated_cost,
                used=self.estimated_cost,
            )

    def _check_warnings(self) -> None:
        """Emit a warning log when usage crosses the warning threshold."""
        if self._warning_threshold >= 1.0:
            return

        checks: list[tuple[str, int | float, int | float | None]] = [
            ("total_tokens", self.total_tokens_used, self._max_total_tokens),
            ("input_tokens", self.input_tokens_used, self._max_input_tokens),
            ("output_tokens", self.output_tokens_used, self._max_output_tokens),
            ("estimated_cost", self.estimated_cost, self._max_estimated_cost),
        ]

        for name, used, limit in checks:
            if limit is None:
                continue
            if name in self._warnings_emitted:
                continue
            if used >= limit * self._warning_threshold:
                logger.warning(
                    "TokenBudgetMiddleware: %s at %.0f%% of budget (%s / %s).",
                    name,
                    (used / limit) * 100 if limit else 0,
                    used,
                    limit,
                )
                self._warnings_emitted.add(name)


# ---------------------------------------------------------------------------
# CircuitBreakerMiddleware
# ---------------------------------------------------------------------------


class CircuitBreakerMiddleware(ChatMiddleware):
    """Chat middleware implementing the circuit breaker pattern for LLM calls.

    Monitors consecutive failures (exceptions from downstream) and trips
    open after a configurable threshold.  While open, all calls are
    immediately rejected with
    :exc:`~agent_framework.exceptions.CircuitBreakerOpenException`.
    After a reset timeout, one probe request is allowed through
    (half-open).  If it succeeds, the breaker resets to closed; if it
    fails, the breaker returns to open.

    Args:
        failure_threshold: Number of consecutive failures before the
            circuit opens.
        reset_timeout_seconds: Seconds to wait in the open state before
            transitioning to half-open.
        success_threshold: Number of consecutive successes required in
            the half-open state to transition back to closed.
        excluded_exceptions: Exception types that should **not** count
            as failures (e.g., ``ValueError`` from bad user input).

    Examples:

        .. code-block:: python

            from agent_framework import Agent, CircuitBreakerMiddleware

            breaker = CircuitBreakerMiddleware(
                failure_threshold=3,
                reset_timeout_seconds=30.0,
            )
            agent = Agent(client=client, middleware=[breaker])

            try:
                result = await agent.run("Hello")
            except CircuitBreakerOpenException:
                print("LLM provider is down, try again later")
    """

    def __init__(
        self,
        *,
        failure_threshold: int = 5,
        reset_timeout_seconds: float = 60.0,
        success_threshold: int = 1,
        excluded_exceptions: tuple[type[Exception], ...] = (),
    ) -> None:
        self._failure_threshold = failure_threshold
        self._reset_timeout_seconds = reset_timeout_seconds
        self._success_threshold = success_threshold
        self._excluded_exceptions = excluded_exceptions

        self._state = CircuitBreakerState.CLOSED
        self._consecutive_failures = 0
        self._consecutive_successes_in_half_open = 0
        self._last_failure_time: float | None = None
        self._lock = asyncio.Lock()

    # -- Public properties ---------------------------------------------------

    @property
    def state(self) -> CircuitBreakerState:
        """Current state of the circuit breaker."""
        return self._state

    @property
    def failure_count(self) -> int:
        """Number of consecutive failures recorded."""
        return self._consecutive_failures

    # -- Public methods ------------------------------------------------------

    async def reset(self) -> None:
        """Manually reset the circuit breaker to the closed state."""
        async with self._lock:
            self._state = CircuitBreakerState.CLOSED
            self._consecutive_failures = 0
            self._consecutive_successes_in_half_open = 0
            self._last_failure_time = None
            logger.info("CircuitBreakerMiddleware: manually reset to CLOSED.")

    # -- ChatMiddleware implementation ---------------------------------------

    async def process(
        self,
        context: ChatContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:
        """Apply circuit breaker logic around the LLM call.

        Args:
            context: Chat invocation context.
            call_next: Callable to pass control to the next middleware.

        Raises:
            CircuitBreakerOpenException: When the circuit is open and
                the reset timeout has not yet elapsed.
        """
        async with self._lock:
            self._maybe_transition_to_half_open()

            if self._state == CircuitBreakerState.OPEN:
                raise CircuitBreakerOpenException(
                    f"Circuit breaker is open after {self._consecutive_failures} consecutive failures. "
                    f"Will probe again in {self._seconds_until_half_open():.1f}s.",
                    failure_count=self._consecutive_failures,
                    threshold=self._failure_threshold,
                )

        # Allow the call through (CLOSED or HALF_OPEN).
        try:
            await call_next()
        except Exception as exc:
            if isinstance(exc, tuple(self._excluded_exceptions)):
                raise

            async with self._lock:
                self._consecutive_failures += 1
                self._consecutive_successes_in_half_open = 0

                if self._consecutive_failures >= self._failure_threshold:
                    self._state = CircuitBreakerState.OPEN
                    self._last_failure_time = time.monotonic()
                    logger.warning(
                        "CircuitBreakerMiddleware: circuit tripped OPEN after %d consecutive failures.",
                        self._consecutive_failures,
                    )
                elif self._state == CircuitBreakerState.HALF_OPEN:
                    self._state = CircuitBreakerState.OPEN
                    self._last_failure_time = time.monotonic()
                    logger.warning(
                        "CircuitBreakerMiddleware: half-open probe failed, returning to OPEN.",
                    )

            raise
        else:
            async with self._lock:
                self._consecutive_failures = 0

                if self._state == CircuitBreakerState.HALF_OPEN:
                    self._consecutive_successes_in_half_open += 1
                    if self._consecutive_successes_in_half_open >= self._success_threshold:
                        self._state = CircuitBreakerState.CLOSED
                        self._consecutive_successes_in_half_open = 0
                        logger.info("CircuitBreakerMiddleware: half-open probe succeeded, circuit CLOSED.")

    # -- Internal helpers ----------------------------------------------------

    def _maybe_transition_to_half_open(self) -> None:
        """Transition from OPEN to HALF_OPEN if the reset timeout has elapsed.

        Must be called while holding ``self._lock``.
        """
        if self._state != CircuitBreakerState.OPEN:
            return

        if self._last_failure_time is None:
            return

        elapsed = time.monotonic() - self._last_failure_time
        if elapsed >= self._reset_timeout_seconds:
            self._state = CircuitBreakerState.HALF_OPEN
            self._consecutive_successes_in_half_open = 0
            logger.info(
                "CircuitBreakerMiddleware: reset timeout elapsed (%.1fs), transitioning to HALF_OPEN.",
                elapsed,
            )

    def _seconds_until_half_open(self) -> float:
        """Return seconds remaining until the circuit transitions to half-open.

        Must be called while holding ``self._lock``.
        """
        if self._last_failure_time is None:
            return 0.0
        elapsed = time.monotonic() - self._last_failure_time
        return max(0.0, self._reset_timeout_seconds - elapsed)
