# Copyright (c) Microsoft. All rights reserved.

import asyncio
from collections.abc import AsyncIterable, Awaitable, Callable
from random import randint
from typing import Annotated

from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    AgentRunContext,
    ChatMessage,
    Role,
    TextContent,
    tool,
)
from agent_framework.azure import AzureAIAgentClient
from azure.identity.aio import AzureCliCredential
from pydantic import Field

"""
Result Override with Middleware (Regular and Streaming)

This sample demonstrates how to use middleware to intercept and modify function results
after execution, supporting both regular and streaming agent responses. The example shows:

- How to execute the original function first and then modify its result
- Replacing function outputs with custom messages or transformed data
- Using middleware for result filtering, formatting, or enhancement
- Detecting streaming vs non-streaming execution using context.is_streaming
- Overriding streaming results with custom async generators

The weather override middleware lets the original weather function execute normally,
then replaces its result with a custom "perfect weather" message. For streaming responses,
it creates a custom async generator that yields the override message in chunks.
"""

# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production; see samples/getting_started/tools/function_tool_with_approval.py and samples/getting_started/tools/function_tool_with_approval_and_threads.py.
@tool(approval_mode="never_require")

def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def weather_override_middleware(
    context: AgentRunContext, next: Callable[[AgentRunContext], Awaitable[None]]
) -> None:
    """Middleware that overrides weather results for both streaming and non-streaming cases."""

    # Let the original agent execution complete first
    await next(context)

    # Check if there's a result to override (agent called weather function)
    if context.result is not None:
        # Create custom weather message
        chunks = [
            "Weather Advisory - ",
            "due to special atmospheric conditions, ",
            "all locations are experiencing perfect weather today! ",
            "Temperature is a comfortable 22°C with gentle breezes. ",
            "Perfect day for outdoor activities!",
        ]

        if context.is_streaming:
            # For streaming: create an async generator that yields chunks
            async def override_stream() -> AsyncIterable[AgentResponseUpdate]:
                for chunk in chunks:
                    yield AgentResponseUpdate(contents=[TextContent(text=chunk)])

            context.result = override_stream()
        else:
            # For non-streaming: just replace with the string message
            custom_message = "".join(chunks)
            context.result = AgentResponse(messages=[ChatMessage(role=Role.ASSISTANT, text=custom_message)])


async def main() -> None:
    """Example demonstrating result override with middleware for both streaming and non-streaming."""
    print("=== Result Override Middleware Example ===")

    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    async with (
        AzureCliCredential() as credential,
        AzureAIAgentClient(credential=credential).as_agent(
            name="WeatherAgent",
            instructions="You are a helpful weather assistant. Use the weather tool to get current conditions.",
            tools=get_weather,
            middleware=[weather_override_middleware],
        ) as agent,
    ):
        # Non-streaming example
        print("\n--- Non-streaming Example ---")
        query = "What's the weather like in Seattle?"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result}")

        # Streaming example
        print("\n--- Streaming Example ---")
        query = "What's the weather like in Portland?"
        print(f"User: {query}")
        print("Agent: ", end="", flush=True)
        async for chunk in agent.run_stream(query):
            if chunk.text:
                print(chunk.text, end="", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
