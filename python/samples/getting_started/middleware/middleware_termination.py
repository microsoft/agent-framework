# Copyright (c) Microsoft. All rights reserved.

import asyncio
from collections.abc import Awaitable, Callable
from random import randint
from typing import Annotated

from agent_framework import (
    AgentMiddleware,
    AgentRunContext,
    AgentRunResponse,
    ChatMessage,
    Role,
)
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from pydantic import Field

"""
Middleware Termination Example

This sample demonstrates how middleware can terminate execution using the `context.terminate` flag.
The example includes:

- PreTerminationMiddleware: Terminates execution before calling next() to prevent agent processing
- PostTerminationMiddleware: Allows processing to complete but terminates further execution

This is useful for implementing security checks, rate limiting, or early exit conditions.
"""


def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


class PreTerminationMiddleware(AgentMiddleware):
    """Middleware that terminates execution before calling the agent."""

    def __init__(self, blocked_words: list[str]):
        self.blocked_words = [word.lower() for word in blocked_words]

    async def process(
        self,
        context: AgentRunContext,
        next: Callable[[AgentRunContext], Awaitable[None]],
    ) -> None:
        # Check if the user message contains any blocked words
        last_message = context.messages[-1] if context.messages else None
        if last_message and last_message.text:
            query = last_message.text.lower()
            for blocked_word in self.blocked_words:
                if blocked_word in query:
                    print(f"[PreTerminationMiddleware] Blocked word '{blocked_word}' detected. Terminating request.")

                    # Set a custom response
                    context.result = AgentRunResponse(
                        messages=[
                            ChatMessage(
                                role=Role.ASSISTANT,
                                text=(
                                    f"Sorry, I cannot process requests containing '{blocked_word}'. "
                                    "Please rephrase your question."
                                ),
                            )
                        ]
                    )

                    # Set terminate flag to prevent further processing
                    context.terminate = True
                    break

        await next(context)


class PostTerminationMiddleware(AgentMiddleware):
    """Middleware that allows processing but terminates after reaching max responses across multiple runs."""

    def __init__(self, max_responses: int = 1):
        self.max_responses = max_responses
        self.response_count = 0

    async def process(
        self,
        context: AgentRunContext,
        next: Callable[[AgentRunContext], Awaitable[None]],
    ) -> None:
        print(f"[PostTerminationMiddleware] Processing request (response count: {self.response_count})")

        # Check if we should terminate before processing
        if self.response_count >= self.max_responses:
            print(
                f"[PostTerminationMiddleware] Maximum responses ({self.max_responses}) reached. "
                "Terminating further processing."
            )
            context.terminate = True

        # Allow the agent to process normally
        await next(context)

        # Increment response count after processing
        self.response_count += 1


async def pre_termination_middleware() -> None:
    """Demonstrate pre-termination middleware that blocks requests with certain words."""
    print("\n--- Example 1: Pre-termination Middleware ---")
    async with (
        AzureCliCredential() as credential,
        FoundryChatClient(async_credential=credential).create_agent(
            name="WeatherAgent",
            instructions="You are a helpful weather assistant.",
            tools=get_weather,
            middleware=PreTerminationMiddleware(blocked_words=["bad", "inappropriate"]),
        ) as agent,
    ):
        # Test with normal query
        print("\n1. Normal query:")
        query = "What's the weather like in Seattle?"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result.text}")

        # Test with blocked word
        print("\n2. Query with blocked word:")
        query = "What's the bad weather in New York?"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result.text}")


async def post_termination_middleware() -> None:
    """Demonstrate post-termination middleware that limits responses across multiple runs."""
    print("\n--- Example 2: Post-termination Middleware ---")
    async with (
        AzureCliCredential() as credential,
        FoundryChatClient(async_credential=credential).create_agent(
            name="WeatherAgent",
            instructions="You are a helpful weather assistant.",
            tools=get_weather,
            middleware=PostTerminationMiddleware(max_responses=1),
        ) as agent,
    ):
        # First run (should work)
        print("\n1. First run:")
        query = "What's the weather in Paris?"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result.text}")

        # Second run (should be terminated by middleware)
        print("\n2. Second run (should be terminated):")
        query = "What about the weather in London?"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result.text if result.text else 'No response (terminated)'}")

        # Third run (should also be terminated)
        print("\n3. Third run (should also be terminated):")
        query = "And New York?"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result.text if result.text else 'No response (terminated)'}")


async def main() -> None:
    """Example demonstrating middleware termination functionality."""
    print("=== Middleware Termination Example ===")
    await pre_termination_middleware()
    await post_termination_middleware()


if __name__ == "__main__":
    asyncio.run(main())
