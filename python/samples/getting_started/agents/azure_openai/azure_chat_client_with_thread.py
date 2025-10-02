# Copyright (c) Microsoft. All rights reserved.

import asyncio
from random import randint
from typing import Annotated

from agent_framework import AgentThread, ChatAgent, ChatMessageStore
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential
from pydantic import Field

"""
Azure OpenAI Chat Client with Thread Management Example

This sample demonstrates thread management with Azure OpenAI Chat Client, comparing
automatic thread creation with explicit thread management for persistent context.
"""


def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def example_with_automatic_thread_creation() -> None:
    """Example showing automatic thread creation (service-managed thread)."""
    print("=== Automatic Thread Creation Example ===")

    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    agent = ChatAgent(
        chat_client=AzureOpenAIChatClient(credential=AzureCliCredential()),
        instructions="You are a helpful weather agent.",
        tools=get_weather,
    )

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


async def example_with_thread_persistence() -> None:
    """Example showing thread persistence across multiple conversations."""
    print("=== Thread Persistence Example ===")
    print("Using the same thread across multiple conversations to maintain context.\n")

    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    agent = ChatAgent(
        chat_client=AzureOpenAIChatClient(credential=AzureCliCredential()),
        instructions="You are a helpful weather agent.",
        tools=get_weather,
    )

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


async def example_with_existing_thread_messages() -> None:
    """Example showing how to work with existing thread messages for Azure."""
    print("=== Existing Thread Messages Example ===")

    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    agent = ChatAgent(
        chat_client=AzureOpenAIChatClient(credential=AzureCliCredential()),
        instructions="You are a helpful weather agent.",
        tools=get_weather,
    )

    # Start a conversation and build up message history
    thread = agent.get_new_thread()

    query1 = "What's the weather in Paris?"
    print(f"User: {query1}")
    result1 = await agent.run(query1, thread=thread)
    print(f"Agent: {result1.text}")

    # The thread now contains the conversation history in memory
    if thread.message_store:
        messages = await thread.message_store.list_messages()
        print(f"Thread contains {len(messages or [])} messages")

    print("\n--- Continuing with the same thread in a new agent instance ---")

    # Create a new agent instance but use the existing thread with its message history
    new_agent = ChatAgent(
        chat_client=AzureOpenAIChatClient(credential=AzureCliCredential()),
        instructions="You are a helpful weather agent.",
        tools=get_weather,
    )

    # Use the same thread object which contains the conversation history
    query2 = "What was the last city I asked about?"
    print(f"User: {query2}")
    result2 = await new_agent.run(query2, thread=thread)
    print(f"Agent: {result2.text}")
    print("Note: The agent continues the conversation using the local message history.\n")

    print("\n--- Alternative: Creating a new thread from existing messages ---")

    # You can also create a new thread from existing messages
    messages = await thread.message_store.list_messages() if thread.message_store else []
    new_thread = AgentThread(message_store=ChatMessageStore(messages))

    query3 = "How does the Paris weather compare to London?"
    print(f"User: {query3}")
    result3 = await new_agent.run(query3, thread=new_thread)
    print(f"Agent: {result3.text}")
    print("Note: This creates a new thread with the same conversation history.\n")


async def main() -> None:
    print("=== Azure Chat Client Agent Thread Management Examples ===\n")

    await example_with_automatic_thread_creation()
    await example_with_thread_persistence()
    await example_with_existing_thread_messages()


if __name__ == "__main__":
    asyncio.run(main())
