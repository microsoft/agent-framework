# Copyright (c) Microsoft. All rights reserved.

import asyncio
import time
from collections.abc import Awaitable, Callable
from random import randint
from typing import Annotated

from agent_framework import (
    AgentRunContext,
    FunctionInvocationContext,
)
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from pydantic import Field

"""
Function-based Middleware Example

This sample demonstrates how to implement middleware using simple async functions instead of classes.
The example includes:

- Security middleware that validates agent requests for sensitive information
- Logging middleware that tracks function execution timing and parameters
- Performance monitoring to measure execution duration

Function-based middleware is ideal for simple, stateless operations and provides a more
lightweight approach compared to class-based middleware. Both agent and function middleware
can be implemented as async functions that accept context and next parameters.
"""


def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def security_agent_middleware(
    context: AgentRunContext,
    next: Callable[[AgentRunContext], Awaitable[None]],
) -> None:
    """Agent middleware that checks for security violations."""
    # Check for potential security violations in the query
    # For this example, we'll check the last user message
    last_message = context.messages[-1] if context.messages else None
    if last_message and last_message.text:
        query = last_message.text
        if "password" in query.lower() or "secret" in query.lower():
            print("[SecurityAgentMiddleware] Security Warning: Detected sensitive information, blocking request.")
            # Simply don't call next() to prevent execution
            return

    print("[SecurityAgentMiddleware] Security check passed.")
    await next(context)


async def logging_function_middleware(
    context: FunctionInvocationContext,
    next: Callable[[FunctionInvocationContext], Awaitable[None]],
) -> None:
    """Function middleware that logs function calls."""
    function_name = context.function.name
    print(f"[LoggingFunctionMiddleware] About to call function: {function_name}.")

    start_time = time.time()

    await next(context)

    end_time = time.time()
    duration = end_time - start_time

    print(f"[LoggingFunctionMiddleware] Function {function_name} completed in {duration:.5f}s.")


async def main() -> None:
    """Example demonstrating function-based middleware."""
    print("=== Function-based Middleware Example ===")

    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    async with (
        AzureCliCredential() as credential,
        FoundryChatClient(async_credential=credential).create_agent(
            name="WeatherAgent",
            instructions="You are a helpful weather assistant.",
            tools=get_weather,
            middleware=[security_agent_middleware, logging_function_middleware],
        ) as agent,
    ):
        # Test with normal query
        print("\n--- Normal Query ---")
        query = "What's the weather like in Tokyo?"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result.text if result.text else 'No response'}\n")

        # Test with security violation
        print("--- Security Test ---")
        query = "What's the secret weather password?"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result.text if result.text else 'No response'}\n")


if __name__ == "__main__":
    asyncio.run(main())
