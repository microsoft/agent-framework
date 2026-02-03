# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from datetime import datetime, timezone
from random import randint
from typing import Annotated

from agent_framework.openai import OpenAIAssistantProvider
from openai import AsyncOpenAI
from pydantic import Field
from agent_framework import tool

"""
OpenAI Assistants with Function Tools Example

This sample demonstrates function tool integration with OpenAI Assistants,
showing both agent-level and query-level tool configuration patterns.
"""

# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production; see samples/getting_started/tools/function_tool_with_approval.py and samples/getting_started/tools/function_tool_with_approval_and_threads.py.
@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}C."

@tool(approval_mode="never_require")
def get_time() -> str:
    """Get the current UTC time."""
    current_time = datetime.now(timezone.utc)
    return f"The current UTC time is {current_time.strftime('%Y-%m-%d %H:%M:%S')}."


async def tools_on_agent_level() -> None:
    """Example showing tools defined when creating the agent."""
    print("=== Tools Defined on Agent Level ===")

    client = AsyncOpenAI()
    provider = OpenAIAssistantProvider(client)

    # Tools are provided when creating the agent
    # The agent can use these tools for any query during its lifetime
    agent = await provider.create_agent(
        name="InfoAssistant",
        model=os.environ.get("OPENAI_CHAT_MODEL_ID", "gpt-4"),
        instructions="You are a helpful assistant that can provide weather and time information.",
        tools=[get_weather, get_time],  # Tools defined at agent creation
    )

    try:
        # First query - agent can use weather tool
        query1 = "What's the weather like in New York?"
        print(f"User: {query1}")
        result1 = await agent.run(query1)
        print(f"Agent: {result1}\n")

        # Second query - agent can use time tool
        query2 = "What's the current UTC time?"
        print(f"User: {query2}")
        result2 = await agent.run(query2)
        print(f"Agent: {result2}\n")

        # Third query - agent can use both tools if needed
        query3 = "What's the weather in London and what's the current UTC time?"
        print(f"User: {query3}")
        result3 = await agent.run(query3)
        print(f"Agent: {result3}\n")
    finally:
        await client.beta.assistants.delete(agent.id)


async def tools_on_run_level() -> None:
    """Example showing tools passed to the run method."""
    print("=== Tools Passed to Run Method ===")

    client = AsyncOpenAI()
    provider = OpenAIAssistantProvider(client)

    # Agent created with base tools, additional tools can be passed at run time
    agent = await provider.create_agent(
        name="FlexibleAssistant",
        model=os.environ.get("OPENAI_CHAT_MODEL_ID", "gpt-4"),
        instructions="You are a helpful assistant.",
        tools=[get_weather],  # Base tool
    )

    try:
        # First query using base weather tool
        query1 = "What's the weather like in Seattle?"
        print(f"User: {query1}")
        result1 = await agent.run(query1)
        print(f"Agent: {result1}\n")

        # Second query with additional time tool
        query2 = "What's the current UTC time?"
        print(f"User: {query2}")
        result2 = await agent.run(query2, tools=[get_time])  # Additional tool for this query
        print(f"Agent: {result2}\n")

        # Third query with both tools
        query3 = "What's the weather in Chicago and what's the current UTC time?"
        print(f"User: {query3}")
        result3 = await agent.run(query3, tools=[get_time])  # Time tool adds to weather
        print(f"Agent: {result3}\n")
    finally:
        await client.beta.assistants.delete(agent.id)


async def mixed_tools_example() -> None:
    """Example showing both agent-level tools and run-method tools."""
    print("=== Mixed Tools Example (Agent + Run Method) ===")

    client = AsyncOpenAI()
    provider = OpenAIAssistantProvider(client)

    # Agent created with some base tools
    agent = await provider.create_agent(
        name="ComprehensiveAssistant",
        model=os.environ.get("OPENAI_CHAT_MODEL_ID", "gpt-4"),
        instructions="You are a comprehensive assistant that can help with various information requests.",
        tools=[get_weather],  # Base tool available for all queries
    )

    try:
        # Query using both agent tool and additional run-method tools
        query = "What's the weather in Denver and what's the current UTC time?"
        print(f"User: {query}")

        # Agent has access to get_weather (from creation) + additional tools from run method
        result = await agent.run(
            query,
            tools=[get_time],  # Additional tools for this specific query
        )
        print(f"Agent: {result}\n")
    finally:
        await client.beta.assistants.delete(agent.id)


async def main() -> None:
    print("=== OpenAI Assistants Provider with Function Tools Examples ===\n")

    await tools_on_agent_level()
    await tools_on_run_level()
    await mixed_tools_example()


if __name__ == "__main__":
    asyncio.run(main())
