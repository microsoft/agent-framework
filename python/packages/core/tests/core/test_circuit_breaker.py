# Copyright (c) Microsoft. All rights reserved.

"""Tests for circuit breaker and token budget middleware."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

import pytest

from agent_framework import (
    Agent,
    ChatContext,
    ChatMiddleware,
    ChatResponse,
    CircuitBreakerMiddleware,
    CircuitBreakerOpenException,
    CircuitBreakerState,
    Message,
    TokenBudgetExceededException,
    TokenBudgetMiddleware,
    UsageDetails,
)

from .conftest import MockBaseChatClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _response_with_usage(
    *,
    input_tokens: int = 100,
    output_tokens: int = 50,
    total_tokens: int | None = None,
) -> ChatResponse:
    """Create a ChatResponse with usage details."""
    return ChatResponse(
        messages=Message(role="assistant", contents=["test response"]),
        usage_details=UsageDetails(
            input_token_count=input_tokens,
            output_token_count=output_tokens,
            total_token_count=total_tokens if total_tokens is not None else input_tokens + output_tokens,
        ),
    )


def _response_without_usage() -> ChatResponse:
    """Create a ChatResponse without usage details."""
    return ChatResponse(
        messages=Message(role="assistant", contents=["test response"]),
    )


class _FailingChatMiddleware(ChatMiddleware):
    """Middleware that raises an exception to simulate LLM failures."""

    def __init__(self, exception: Exception) -> None:
        self._exception = exception

    async def process(
        self,
        context: ChatContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:
        raise self._exception


# ---------------------------------------------------------------------------
# TokenBudgetMiddleware Tests
# ---------------------------------------------------------------------------


class TestTokenBudgetMiddleware:
    """Tests for TokenBudgetMiddleware."""

    async def test_allows_calls_within_budget(self, chat_client_base: MockBaseChatClient) -> None:
        """Calls within budget should pass through normally."""
        chat_client_base.run_responses = [_response_with_usage(input_tokens=50, output_tokens=30)]

        budget = TokenBudgetMiddleware(max_total_tokens=1000)
        chat_client_base.chat_middleware = [budget]

        messages = [Message(role="user", contents=["hello"])]
        response = await chat_client_base.get_response(messages)

        assert response is not None
        assert budget.total_tokens_used == 80

    async def test_accumulates_usage_across_calls(self, chat_client_base: MockBaseChatClient) -> None:
        """Usage should accumulate across multiple calls."""
        chat_client_base.run_responses = [
            _response_with_usage(input_tokens=100, output_tokens=50),
            _response_with_usage(input_tokens=200, output_tokens=100),
        ]

        budget = TokenBudgetMiddleware(max_total_tokens=10000)
        chat_client_base.chat_middleware = [budget]

        messages = [Message(role="user", contents=["hello"])]
        await chat_client_base.get_response(messages)
        assert budget.total_tokens_used == 150
        assert budget.input_tokens_used == 100
        assert budget.output_tokens_used == 50

        await chat_client_base.get_response(messages)
        assert budget.total_tokens_used == 450
        assert budget.input_tokens_used == 300
        assert budget.output_tokens_used == 150

    async def test_blocks_before_call_when_already_exceeded(self, chat_client_base: MockBaseChatClient) -> None:
        """Pre-call check should raise without calling the LLM."""
        chat_client_base.run_responses = [
            _response_with_usage(input_tokens=500, output_tokens=500),
        ]

        budget = TokenBudgetMiddleware(max_total_tokens=100)
        chat_client_base.chat_middleware = [budget]

        messages = [Message(role="user", contents=["hello"])]

        # First call exceeds budget on post-check.
        with pytest.raises(TokenBudgetExceededException):
            await chat_client_base.get_response(messages)

        assert chat_client_base.call_count == 1

        # Second call should fail on pre-check without calling the LLM.
        with pytest.raises(TokenBudgetExceededException) as exc_info:
            await chat_client_base.get_response(messages)

        assert chat_client_base.call_count == 1  # NOT incremented
        assert exc_info.value.budget == 100
        assert exc_info.value.used == 1000

    async def test_raises_after_call_when_limit_crossed(self, chat_client_base: MockBaseChatClient) -> None:
        """Exception should carry correct budget and used values."""
        chat_client_base.run_responses = [
            _response_with_usage(input_tokens=600, output_tokens=600),
        ]

        budget = TokenBudgetMiddleware(max_total_tokens=500)
        chat_client_base.chat_middleware = [budget]

        messages = [Message(role="user", contents=["hello"])]
        with pytest.raises(TokenBudgetExceededException) as exc_info:
            await chat_client_base.get_response(messages)

        assert exc_info.value.budget == 500
        assert exc_info.value.used == 1200

    async def test_input_token_limit(self, chat_client_base: MockBaseChatClient) -> None:
        """Independent input token cap should work."""
        chat_client_base.run_responses = [
            _response_with_usage(input_tokens=200, output_tokens=10),
        ]

        budget = TokenBudgetMiddleware(max_input_tokens=100)
        chat_client_base.chat_middleware = [budget]

        messages = [Message(role="user", contents=["hello"])]
        with pytest.raises(TokenBudgetExceededException) as exc_info:
            await chat_client_base.get_response(messages)

        assert exc_info.value.budget == 100
        assert exc_info.value.used == 200

    async def test_output_token_limit(self, chat_client_base: MockBaseChatClient) -> None:
        """Independent output token cap should work."""
        chat_client_base.run_responses = [
            _response_with_usage(input_tokens=10, output_tokens=200),
        ]

        budget = TokenBudgetMiddleware(max_output_tokens=100)
        chat_client_base.chat_middleware = [budget]

        messages = [Message(role="user", contents=["hello"])]
        with pytest.raises(TokenBudgetExceededException) as exc_info:
            await chat_client_base.get_response(messages)

        assert exc_info.value.budget == 100
        assert exc_info.value.used == 200

    async def test_estimated_cost_limit(self, chat_client_base: MockBaseChatClient) -> None:
        """Cost-based budgeting should work."""
        chat_client_base.run_responses = [
            _response_with_usage(input_tokens=1000, output_tokens=500),
        ]

        budget = TokenBudgetMiddleware(
            max_estimated_cost=0.01,
            cost_per_input_token=0.00001,  # $10/M input
            cost_per_output_token=0.00003,  # $30/M output
        )
        chat_client_base.chat_middleware = [budget]

        messages = [Message(role="user", contents=["hello"])]
        with pytest.raises(TokenBudgetExceededException) as exc_info:
            await chat_client_base.get_response(messages)

        # Cost = 1000*0.00001 + 500*0.00003 = 0.01 + 0.015 = 0.025
        assert exc_info.value.budget == 0.01
        assert exc_info.value.used == pytest.approx(0.025)

    async def test_warning_threshold_logs_warning(
        self, chat_client_base: MockBaseChatClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Warning should be emitted at the configured threshold."""
        chat_client_base.run_responses = [
            _response_with_usage(input_tokens=40, output_tokens=45),
        ]

        budget = TokenBudgetMiddleware(max_total_tokens=100, warning_threshold=0.8)
        chat_client_base.chat_middleware = [budget]

        messages = [Message(role="user", contents=["hello"])]
        with caplog.at_level(logging.WARNING, logger="agent_framework"):
            # 85 tokens = 85% of 100, exceeds 80% threshold
            await chat_client_base.get_response(messages)

        assert any("total_tokens" in record.message and "85%" in record.message for record in caplog.records)

    async def test_reset_clears_counters(self, chat_client_base: MockBaseChatClient) -> None:
        """Reset should zero all counters."""
        chat_client_base.run_responses = [
            _response_with_usage(input_tokens=100, output_tokens=50),
            _response_with_usage(input_tokens=100, output_tokens=50),
        ]

        budget = TokenBudgetMiddleware(max_total_tokens=10000)
        chat_client_base.chat_middleware = [budget]

        messages = [Message(role="user", contents=["hello"])]
        await chat_client_base.get_response(messages)
        assert budget.total_tokens_used == 150

        await budget.reset()
        assert budget.total_tokens_used == 0
        assert budget.input_tokens_used == 0
        assert budget.output_tokens_used == 0
        assert budget.estimated_cost == 0.0

        await chat_client_base.get_response(messages)
        assert budget.total_tokens_used == 150

    def test_no_limits_raises_valueerror(self) -> None:
        """Creating without any limits should raise ValueError."""
        with pytest.raises(ValueError, match="At least one limit must be configured"):
            TokenBudgetMiddleware()

    def test_cost_without_rates_raises_valueerror(self) -> None:
        """Cost limit without rates should raise ValueError."""
        with pytest.raises(ValueError, match="max_estimated_cost requires"):
            TokenBudgetMiddleware(max_estimated_cost=1.0)

    async def test_handles_missing_usage_details(
        self, chat_client_base: MockBaseChatClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Missing usage_details should log debug, not crash."""
        chat_client_base.run_responses = [_response_without_usage()]

        budget = TokenBudgetMiddleware(max_total_tokens=1000)
        chat_client_base.chat_middleware = [budget]

        messages = [Message(role="user", contents=["hello"])]
        with caplog.at_level(logging.DEBUG, logger="agent_framework"):
            response = await chat_client_base.get_response(messages)

        assert response is not None
        assert budget.total_tokens_used == 0

    async def test_with_agent_integration(self) -> None:
        """Full Agent + MockBaseChatClient pipeline."""
        client = MockBaseChatClient()
        client.run_responses = [
            _response_with_usage(input_tokens=500, output_tokens=600),
        ]

        budget = TokenBudgetMiddleware(max_total_tokens=100)
        agent = Agent(client=client, instructions="test", middleware=[budget])

        with pytest.raises(TokenBudgetExceededException):
            await agent.run("hello")


# ---------------------------------------------------------------------------
# CircuitBreakerMiddleware Tests
# ---------------------------------------------------------------------------


class TestCircuitBreakerMiddleware:
    """Tests for CircuitBreakerMiddleware."""

    async def test_closed_allows_calls(self, chat_client_base: MockBaseChatClient) -> None:
        """Normal operation should pass through."""
        breaker = CircuitBreakerMiddleware(failure_threshold=3)
        chat_client_base.chat_middleware = [breaker]

        messages = [Message(role="user", contents=["hello"])]
        response = await chat_client_base.get_response(messages)

        assert response is not None
        assert breaker.state == CircuitBreakerState.CLOSED
        assert breaker.failure_count == 0

    async def test_trips_after_threshold(self, chat_client_base: MockBaseChatClient) -> None:
        """N consecutive failures should trip the circuit to OPEN."""
        breaker = CircuitBreakerMiddleware(failure_threshold=3)
        failing = _FailingChatMiddleware(RuntimeError("LLM down"))
        chat_client_base.chat_middleware = [breaker, failing]

        messages = [Message(role="user", contents=["hello"])]
        for _ in range(3):
            with pytest.raises(RuntimeError, match="LLM down"):
                await chat_client_base.get_response(messages)

        assert breaker.state == CircuitBreakerState.OPEN
        assert breaker.failure_count == 3

    async def test_open_blocks_immediately(self, chat_client_base: MockBaseChatClient) -> None:
        """Open circuit should raise CircuitBreakerOpenException immediately."""
        breaker = CircuitBreakerMiddleware(failure_threshold=2, reset_timeout_seconds=60.0)
        failing = _FailingChatMiddleware(RuntimeError("LLM down"))
        chat_client_base.chat_middleware = [breaker, failing]

        messages = [Message(role="user", contents=["hello"])]

        # Trip the breaker.
        for _ in range(2):
            with pytest.raises(RuntimeError):
                await chat_client_base.get_response(messages)

        assert breaker.state == CircuitBreakerState.OPEN

        # Next call should be blocked without reaching the failing middleware.
        with pytest.raises(CircuitBreakerOpenException) as exc_info:
            await chat_client_base.get_response(messages)

        assert exc_info.value.failure_count == 2
        assert exc_info.value.threshold == 2

    async def test_half_open_after_timeout(self, chat_client_base: MockBaseChatClient) -> None:
        """After reset timeout, circuit should transition to HALF_OPEN."""
        breaker = CircuitBreakerMiddleware(failure_threshold=1, reset_timeout_seconds=0.1)
        failing = _FailingChatMiddleware(RuntimeError("LLM down"))
        chat_client_base.chat_middleware = [breaker, failing]

        messages = [Message(role="user", contents=["hello"])]

        # Trip the breaker.
        with pytest.raises(RuntimeError):
            await chat_client_base.get_response(messages)

        assert breaker.state == CircuitBreakerState.OPEN

        # Wait for reset timeout.
        await asyncio.sleep(0.15)

        # Remove the failing middleware so the probe succeeds.
        chat_client_base.chat_middleware = [breaker]

        response = await chat_client_base.get_response(messages)
        assert response is not None
        assert breaker.state == CircuitBreakerState.CLOSED

    async def test_half_open_success_resets(self, chat_client_base: MockBaseChatClient) -> None:
        """Successful probe in HALF_OPEN should reset to CLOSED."""
        breaker = CircuitBreakerMiddleware(failure_threshold=1, reset_timeout_seconds=0.05)
        failing = _FailingChatMiddleware(RuntimeError("LLM down"))
        chat_client_base.chat_middleware = [breaker, failing]

        messages = [Message(role="user", contents=["hello"])]

        # Trip the breaker.
        with pytest.raises(RuntimeError):
            await chat_client_base.get_response(messages)

        await asyncio.sleep(0.1)

        # Successful probe.
        chat_client_base.chat_middleware = [breaker]
        await chat_client_base.get_response(messages)

        assert breaker.state == CircuitBreakerState.CLOSED
        assert breaker.failure_count == 0

    async def test_half_open_failure_reopens(self, chat_client_base: MockBaseChatClient) -> None:
        """Failed probe in HALF_OPEN should return to OPEN."""
        breaker = CircuitBreakerMiddleware(failure_threshold=1, reset_timeout_seconds=0.05)
        failing = _FailingChatMiddleware(RuntimeError("still down"))
        chat_client_base.chat_middleware = [breaker, failing]

        messages = [Message(role="user", contents=["hello"])]

        # Trip the breaker.
        with pytest.raises(RuntimeError):
            await chat_client_base.get_response(messages)

        await asyncio.sleep(0.1)

        # Probe fails — should re-open.
        with pytest.raises(RuntimeError, match="still down"):
            await chat_client_base.get_response(messages)

        assert breaker.state == CircuitBreakerState.OPEN

    async def test_success_threshold_in_half_open(self, chat_client_base: MockBaseChatClient) -> None:
        """Configurable success_threshold should require N successes."""
        breaker = CircuitBreakerMiddleware(
            failure_threshold=1,
            reset_timeout_seconds=0.05,
            success_threshold=2,
        )
        failing = _FailingChatMiddleware(RuntimeError("down"))
        chat_client_base.chat_middleware = [breaker, failing]

        messages = [Message(role="user", contents=["hello"])]

        # Trip the breaker.
        with pytest.raises(RuntimeError):
            await chat_client_base.get_response(messages)

        await asyncio.sleep(0.1)

        # First success — should stay HALF_OPEN.
        chat_client_base.chat_middleware = [breaker]
        await chat_client_base.get_response(messages)
        assert breaker.state == CircuitBreakerState.HALF_OPEN

        # Second success — should transition to CLOSED.
        await chat_client_base.get_response(messages)
        assert breaker.state == CircuitBreakerState.CLOSED

    async def test_excluded_exceptions_not_counted(self, chat_client_base: MockBaseChatClient) -> None:
        """Excluded exception types should not increment failure count."""
        breaker = CircuitBreakerMiddleware(
            failure_threshold=2,
            excluded_exceptions=(ValueError,),
        )
        failing = _FailingChatMiddleware(ValueError("bad input"))
        chat_client_base.chat_middleware = [breaker, failing]

        messages = [Message(role="user", contents=["hello"])]

        for _ in range(5):
            with pytest.raises(ValueError):
                await chat_client_base.get_response(messages)

        # Should still be CLOSED — ValueErrors are excluded.
        assert breaker.state == CircuitBreakerState.CLOSED
        assert breaker.failure_count == 0

    async def test_success_resets_consecutive_count(self, chat_client_base: MockBaseChatClient) -> None:
        """A successful call should reset the failure counter."""
        breaker = CircuitBreakerMiddleware(failure_threshold=3)
        failing = _FailingChatMiddleware(RuntimeError("fail"))

        messages = [Message(role="user", contents=["hello"])]

        # 2 failures.
        chat_client_base.chat_middleware = [breaker, failing]
        for _ in range(2):
            with pytest.raises(RuntimeError):
                await chat_client_base.get_response(messages)

        assert breaker.failure_count == 2

        # 1 success resets count.
        chat_client_base.chat_middleware = [breaker]
        await chat_client_base.get_response(messages)
        assert breaker.failure_count == 0
        assert breaker.state == CircuitBreakerState.CLOSED

    async def test_manual_reset(self, chat_client_base: MockBaseChatClient) -> None:
        """Manual reset should return to CLOSED."""
        breaker = CircuitBreakerMiddleware(failure_threshold=1)
        failing = _FailingChatMiddleware(RuntimeError("fail"))
        chat_client_base.chat_middleware = [breaker, failing]

        messages = [Message(role="user", contents=["hello"])]

        with pytest.raises(RuntimeError):
            await chat_client_base.get_response(messages)

        assert breaker.state == CircuitBreakerState.OPEN

        await breaker.reset()
        assert breaker.state == CircuitBreakerState.CLOSED
        assert breaker.failure_count == 0

    async def test_with_agent_integration(self) -> None:
        """Full Agent + MockBaseChatClient pipeline."""
        client = MockBaseChatClient()
        breaker = CircuitBreakerMiddleware(failure_threshold=3)
        agent = Agent(client=client, instructions="test", middleware=[breaker])

        result = await agent.run("hello")
        assert result is not None
        assert breaker.state == CircuitBreakerState.CLOSED


# ---------------------------------------------------------------------------
# Combined Tests
# ---------------------------------------------------------------------------


class TestCombinedMiddleware:
    """Tests for using both middleware together."""

    async def test_both_middleware_combined(self, chat_client_base: MockBaseChatClient) -> None:
        """Both middleware should work independently in the same pipeline."""
        chat_client_base.run_responses = [
            _response_with_usage(input_tokens=100, output_tokens=50),
        ]

        breaker = CircuitBreakerMiddleware(failure_threshold=3)
        budget = TokenBudgetMiddleware(max_total_tokens=10000)

        # Circuit breaker registered first (outermost).
        chat_client_base.chat_middleware = [breaker, budget]

        messages = [Message(role="user", contents=["hello"])]
        response = await chat_client_base.get_response(messages)

        assert response is not None
        assert breaker.state == CircuitBreakerState.CLOSED
        assert budget.total_tokens_used == 150
