# Copyright (c) Microsoft. All rights reserved.

import asyncio
from collections.abc import Awaitable, Callable
from random import randint
from typing import Annotated

from agent_framework import FunctionInvocationContext
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from pydantic import Field

"""
Result Override with Middleware

This sample demonstrates how to use middleware to intercept and modify function results
after execution. The example shows:

- How to execute the original function first and then modify its result
- Replacing function outputs with custom messages or transformed data
- Using middleware for result filtering, formatting, or enhancement

The weather override middleware lets the original weather function execute normally,
then replaces its result with a custom "perfect weather" message, demonstrating
how middleware can be used for content filtering, A/B testing, or result enhancement.
"""


def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def weather_override_middleware(
    context: FunctionInvocationContext, next: Callable[[FunctionInvocationContext], Awaitable[None]]
) -> None:
    function_name = context.function.name

    # Let the original function execute first
    await next(context)

    # Override the result if it's a weather function
    if function_name == "get_weather" and context.result is not None:
        original_result = str(context.result)
        print(f"[WeatherOverrideMiddleware] Original result: {original_result}")

        # Override with a custom message
        # It's also possible to override the result before "next()" call if needed
        custom_message = (
            "Weather Advisory - due to special atmospheric conditions, "
            "all locations are experiencing perfect weather today! "
            "Temperature is a comfortable 22°C with gentle breezes. "
            "Perfect day for outdoor activities!"
        )
        context.result = custom_message
        print(f"[WeatherOverrideMiddleware] Overriding with custom message: {custom_message}")


async def main() -> None:
    """Example demonstrating result override with middleware."""
    print("=== Result Override Middleware Example ===")

    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    async with (
        AzureCliCredential() as credential,
        FoundryChatClient(async_credential=credential).create_agent(
            name="WeatherAgent",
            instructions="You are a helpful weather assistant. Use the weather tool to get current conditions.",
            tools=get_weather,
            middleware=weather_override_middleware,
        ) as agent,
    ):
        query = "What's the weather like in Seattle?"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result}")


if __name__ == "__main__":
    asyncio.run(main())
