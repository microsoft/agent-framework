# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "agent-framework",
#     "tenacity",
# ]
# ///
# Run with any PEP 723 compatible runner, e.g.:
#   uv run samples/02-agents/auto_retry.py

# Copyright (c) Microsoft. All rights reserved.

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar, cast

from agent_framework import Agent, ChatContext, ChatMiddleware, SupportsChatGetResponse, chat_middleware
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv
from openai import RateLimitError
from tenacity import (
    AsyncRetrying,
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

# Load environment variables from .env file
load_dotenv()

"""
Auto-Retry Rate Limiting Sample

Every model inference API enforces rate limits, so production agents need retry logic
to handle 429 responses gracefully. This sample shows two ways to add automatic retry
using the `tenacity` library, keeping your application code free of boilerplate.

Approach 1 – Class decorator
    Apply a class decorator to any client type implementing
    SupportsChatGetResponse. The decorator patches get_response() with retry
    behavior. Non-streaming responses are retried; streaming is returned as-is
    (streaming retry requires more delicate handling).

Approach 2 – Chat middleware
    Register middleware on the agent that catches RateLimitError raised inside
    call_next() and retries the entire request pipeline. Two styles are shown:
    a) Class-based middleware (ChatMiddleware subclass)
    b) Function-based middleware (@chat_middleware decorator)

Both approaches use the same tenacity primitives:
    - stop_after_attempt  – cap the total number of tries
    - wait_exponential    – exponential back-off between retries
    - retry_if_exception_type(RateLimitError) – only retry on 429 errors
    - before_sleep_log    – log each retry attempt at WARNING level
"""

logger = logging.getLogger(__name__)

RETRY_ATTEMPTS = 3

# =============================================================================
# Approach 1: Class decorator
# =============================================================================


ChatClientT = TypeVar("ChatClientT", bound=SupportsChatGetResponse[Any])


def with_rate_limit_retry(*, retry_attempts: int = RETRY_ATTEMPTS) -> Callable[[type[ChatClientT]], type[ChatClientT]]:
    """Class decorator that adds non-streaming retry behavior to get_response()."""

    def decorator(client_cls: type[ChatClientT]) -> type[ChatClientT]:
        original_get_response = client_cls.get_response

        def get_response_with_retry(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            stream = kwargs.get("stream", False)

            if stream:
                # Streaming retry is more complex; fall back to the original behaviour.
                return original_get_response(self, *args, **kwargs)

            async def _with_retry():
                async for attempt in AsyncRetrying(
                    stop=stop_after_attempt(retry_attempts),
                    wait=wait_exponential(multiplier=1, min=4, max=10),
                    retry=retry_if_exception_type(RateLimitError),
                    reraise=True,
                    before_sleep=before_sleep_log(logger, logging.WARNING),
                ):
                    with attempt:
                        return await original_get_response(self, *args, **kwargs)
                return None

            return _with_retry()

        client_cls.get_response = cast(Any, get_response_with_retry)
        return client_cls

    return decorator


@with_rate_limit_retry()
class RetryingFoundryChatClient(FoundryChatClient):
    """Azure OpenAI Chat client with class-decorator-based retry behavior."""


# =============================================================================
# Approach 2a: Class-based chat middleware
# =============================================================================


class RateLimitRetryMiddleware(ChatMiddleware):
    """Chat middleware that retries a single model-call pipeline on rate limit errors.

    Register this middleware on an agent (or at the run level) to automatically
    retry any chat-model call that raises RateLimitError. In tool-loop scenarios,
    the middleware applies independently to each inner model call.
    """

    def __init__(self, *, max_attempts: int = RETRY_ATTEMPTS) -> None:
        """Initialize with the maximum number of retry attempts."""
        self.max_attempts = max_attempts

    async def process(
        self,
        context: ChatContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:
        """Retry call_next() on rate limit errors with exponential back-off."""
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self.max_attempts),
            wait=wait_exponential(multiplier=1, min=4, max=10),
            retry=retry_if_exception_type(RateLimitError),
            reraise=True,
            before_sleep=before_sleep_log(logger, logging.WARNING),
        ):
            with attempt:
                await call_next()


# =============================================================================
# Approach 2b: Function-based chat middleware
# =============================================================================


@chat_middleware
async def rate_limit_retry_middleware(
    context: ChatContext,
    call_next: Callable[[], Awaitable[None]],
) -> None:
    """Function-based chat middleware that retries on rate limit errors.

    Wrap call_next() with a tenacity @retry decorator so any RateLimitError
    raised during a single model call triggers an automatic retry with exponential
    back-off. In tool-loop scenarios, the middleware applies independently to
    each inner model call.
    """

    @retry(
        stop=stop_after_attempt(RETRY_ATTEMPTS),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type(RateLimitError),
        reraise=True,
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    async def _call_next_with_retry() -> None:
        await call_next()

    await _call_next_with_retry()


# =============================================================================
# Demo
# =============================================================================


async def class_decorator_example() -> None:
    """Demonstrate Approach 1: class decorator on a chat client type."""
    print("\n" + "=" * 60)
    print("Approach 1: Class decorator (applied to client type)")
    print("=" * 60)

    # For authentication, run `az login` command in terminal or replace
    # AzureCliCredential with your preferred authentication option.
    agent = Agent(
        client=RetryingFoundryChatClient(credential=AzureCliCredential()),
        instructions="You are a helpful assistant.",
    )

    query = "Say hello!"
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Agent: {result.text}")


async def class_based_middleware_example() -> None:
    """Demonstrate Approach 2a: class-based chat middleware."""
    print("\n" + "=" * 60)
    print("Approach 2a: Class-based chat middleware")
    print("=" * 60)

    # For authentication, run `az login` command in terminal or replace
    # AzureCliCredential with your preferred authentication option.
    agent = Agent(
        client=FoundryChatClient(credential=AzureCliCredential()),
        instructions="You are a helpful assistant.",
        middleware=[RateLimitRetryMiddleware(max_attempts=3)],
    )

    query = "Say hello!"
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Agent: {result.text}")


async def function_based_middleware_example() -> None:
    """Demonstrate Approach 2b: function-based chat middleware."""
    print("\n" + "=" * 60)
    print("Approach 2b: Function-based chat middleware")
    print("=" * 60)

    # For authentication, run `az login` command in terminal or replace
    # AzureCliCredential with your preferred authentication option.
    agent = Agent(
        client=FoundryChatClient(credential=AzureCliCredential()),
        instructions="You are a helpful assistant.",
        middleware=[rate_limit_retry_middleware],
    )

    query = "Say hello!"
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Agent: {result.text}")


async def main() -> None:
    """Run all auto-retry examples."""
    print("=== Auto-Retry Rate Limiting Sample ===")
    print(
        "Demonstrates two approaches for automatic retry on rate limit (429) errors.\n"
        "Set AZURE_OPENAI_ENDPOINT and FOUNDRY_MODEL (and optionally\n"
        "AZURE_OPENAI_API_KEY) before running, or populate a .env file."
    )

    await class_decorator_example()
    await class_based_middleware_example()
    await function_based_middleware_example()


if __name__ == "__main__":
    asyncio.run(main())
