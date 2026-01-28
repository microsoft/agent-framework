# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from random import randint
from typing import Annotated

from agent_framework import AgentThread
from agent_framework import tool
from agent_framework.openai import OpenAIAssistantProvider
from openai import AsyncOpenAI
from pydantic import Field

"""
OpenAI Assistants with Thread Management Example

This sample demonstrates thread management with OpenAI Assistants, showing
persistent conversation threads and context preservation across interactions.
"""

# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production; see samples/getting_started/tools/function_tool_with_approval.py and samples/getting_started/tools/function_tool_with_approval_and_threads.py.
@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}C."


async def example_with_automatic_thread_creation() -> None:
    """Example showing automatic thread creation (service-managed thread)."""
    print("=== Automatic Thread Creation Example ===")

    client = AsyncOpenAI()
    provider = OpenAIAssistantProvider(client)

    agent = await provider.create_agent(
        name="WeatherAssistant",
        model=os.environ.get("OPENAI_CHAT_MODEL_ID", "gpt-4"),
        instructions="You are a helpful weather agent.",
        tools=[get_weather],
    )

    try:
        # First conversation - no thread provided, will be created automatically
        query1 = "What's the weather like in Seattle?"
        print(f"User: {query1}")
        result1 = await agent.run(query1)
        print(f"Agent: {result1.text}")

        # Second conversation - still no thread provided, will create another new thread
        query2 = "What was the last city I asked about?"
        print(f"\nUser: {query2}")
        result2 = await agent.run(query2)
        print(f"Agent: {result2.text}")
        print("Note: Each call creates a separate thread, so the agent doesn't remember previous context.\n")
    finally:
        await client.beta.assistants.delete(agent.id)


async def example_with_thread_persistence() -> None:
    """Example showing thread persistence across multiple conversations."""
    print("=== Thread Persistence Example ===")
    print("Using the same thread across multiple conversations to maintain context.\n")

    client = AsyncOpenAI()
    provider = OpenAIAssistantProvider(client)

    agent = await provider.create_agent(
        name="WeatherAssistant",
        model=os.environ.get("OPENAI_CHAT_MODEL_ID", "gpt-4"),
        instructions="You are a helpful weather agent.",
        tools=[get_weather],
    )

    try:
        # Create a new thread that will be reused
        thread = agent.get_new_thread()

        # First conversation
        query1 = "What's the weather like in Tokyo?"
        print(f"User: {query1}")
        result1 = await agent.run(query1, thread=thread)
        print(f"Agent: {result1.text}")

        # Second conversation using the same thread - maintains context
        query2 = "How about London?"
        print(f"\nUser: {query2}")
        result2 = await agent.run(query2, thread=thread)
        print(f"Agent: {result2.text}")

        # Third conversation - agent should remember both previous cities
        query3 = "Which of the cities I asked about has better weather?"
        print(f"\nUser: {query3}")
        result3 = await agent.run(query3, thread=thread)
        print(f"Agent: {result3.text}")
        print("Note: The agent remembers context from previous messages in the same thread.\n")
    finally:
        await client.beta.assistants.delete(agent.id)


async def example_with_existing_thread_id() -> None:
    """Example showing how to work with an existing thread ID from the service."""
    print("=== Existing Thread ID Example ===")
    print("Using a specific thread ID to continue an existing conversation.\n")

    client = AsyncOpenAI()
    provider = OpenAIAssistantProvider(client)

    # First, create a conversation and capture the thread ID
    existing_thread_id = None
    assistant_id = None

    agent = await provider.create_agent(
        name="WeatherAssistant",
        model=os.environ.get("OPENAI_CHAT_MODEL_ID", "gpt-4"),
        instructions="You are a helpful weather agent.",
        tools=[get_weather],
    )
    assistant_id = agent.id

    try:
        # Start a conversation and get the thread ID
        thread = agent.get_new_thread()
        query1 = "What's the weather in Paris?"
        print(f"User: {query1}")
        result1 = await agent.run(query1, thread=thread)
        print(f"Agent: {result1.text}")

        # The thread ID is set after the first response
        existing_thread_id = thread.service_thread_id
        print(f"Thread ID: {existing_thread_id}")

        if existing_thread_id:
            print("\n--- Continuing with the same thread ID using get_agent ---")

            # Get the existing assistant by ID
            agent2 = await provider.get_agent(
                assistant_id=assistant_id,
                tools=[get_weather],  # Must provide function implementations
            )

            # Create a thread with the existing ID
            thread = AgentThread(service_thread_id=existing_thread_id)

            query2 = "What was the last city I asked about?"
            print(f"User: {query2}")
            result2 = await agent2.run(query2, thread=thread)
            print(f"Agent: {result2.text}")
            print("Note: The agent continues the conversation from the previous thread.\n")
    finally:
        if assistant_id:
            await client.beta.assistants.delete(assistant_id)


async def main() -> None:
    print("=== OpenAI Assistants Provider Thread Management Examples ===\n")

    await example_with_automatic_thread_creation()
    await example_with_thread_persistence()
    await example_with_existing_thread_id()


if __name__ == "__main__":
    asyncio.run(main())
