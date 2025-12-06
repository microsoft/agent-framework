# Copyright (c) Microsoft. All rights reserved.

import asyncio
from collections.abc import Awaitable, Callable
from random import randint
from typing import Annotated

from agent_framework import (
    FunctionInvocationContext,
)
from agent_framework.azure import AzureAIAgentClient
from azure.identity.aio import AzureCliCredential
from pydantic import Field

"""
Shared State Function-based Middleware Example

This sample demonstrates how to implement function-based middleware within a class to share state.
The example includes:

- A MiddlewareContainer class with two simple function middleware methods
- First middleware: Counts function calls and stores the count in shared state
- Second middleware: Uses the shared count to add call numbers to function results

This approach shows how middleware can work together by sharing state within the same class instance.
"""


def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


def get_time(
    timezone: Annotated[str, Field(description="The timezone to get the time for.")] = "UTC",
) -> str:
    """Get the current time for a given timezone."""
    import datetime

    return f"The current time in {timezone} is {datetime.datetime.now().strftime('%H:%M:%S')}"


class MiddlewareContainer:
    """Container class that holds middleware functions with shared state."""

    def __init__(self) -> None:
        # Simple shared state: count function calls
        self.call_count: int = 0

    async def call_counter_middleware(
        self,
        context: FunctionInvocationContext,
        next: Callable[[FunctionInvocationContext], Awaitable[None]],
    ) -> None:
        """First middleware: increments call count in shared state."""
        # Increment the shared call count
        self.call_count += 1

        print(f"[CallCounter] This is function call #{self.call_count}")

        # Call the next middleware/function
        await next(context)

    async def result_enhancer_middleware(
        self,
        context: FunctionInvocationContext,
        next: Callable[[FunctionInvocationContext], Awaitable[None]],
    ) -> None:
        """Second middleware: uses shared call count to enhance function results."""
        print(f"[ResultEnhancer] Current total calls so far: {self.call_count}")

        # Call the next middleware/function
        await next(context)

        # After function execution, enhance the result using shared state
        if context.result:
            enhanced_result = f"[Call #{self.call_count}] {context.result}"
            context.result = enhanced_result
            print("[ResultEnhancer] Enhanced result with call number")


async def main() -> None:
    """Example demonstrating shared state function-based middleware."""
    print("=== Shared State Function-based Middleware Example ===")

    # Create middleware container with shared state
    middleware_container = MiddlewareContainer()

    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    async with (
        AzureCliCredential() as credential,
        AzureAIAgentClient(credential=credential).create_agent(
            name="UtilityAgent",
            instructions="You are a helpful assistant that can provide weather information and current time.",
            tools=[get_weather, get_time],
            # Pass both middleware functions from the same container instance
            # Order matters: counter runs first to increment count,
            # then result enhancer uses the updated count
            middleware=[
                middleware_container.call_counter_middleware,
                middleware_container.result_enhancer_middleware,
            ],
        ) as agent,
    ):
        # Test multiple requests to see shared state in action
        queries = [
            "What's the weather like in New York?",
            "What time is it in London?",
            "What's the weather in Tokyo?",
        ]

        for i, query in enumerate(queries, 1):
            print(f"\n--- Query {i} ---")
            print(f"User: {query}")
            result = await agent.run(query)
            print(f"Agent: {result.text if result.text else 'No response'}")

        # Display final statistics
        print("\n=== Final Statistics ===")
        print(f"Total function calls made: {middleware_container.call_count}")


if __name__ == "__main__":
    asyncio.run(main())
