# Copyright (c) Microsoft. All rights reserved.

import asyncio
from random import randint
from typing import Annotated

from agent_framework import AgentThread, ChatAgent
from agent_framework.azure import AzureAIAgentClient
from azure.identity.aio import AzureCliCredential
from pydantic import Field

"""
Azure AI Agent with Thread Management Example

This sample demonstrates thread management with Azure AI Agents, comparing
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
    async with (
        AzureCliCredential() as credential,
        ChatAgent(
            chat_client=AzureAIAgentClient(async_credential=credential),
            instructions="You are a helpful weather agent.",
            tools=get_weather,
        ) as agent,
    ):
        # First conversation - no thread provided, will be created automatically
        first_query = "What's the weather like in Seattle?"
        print(f"User: {first_query}")
        first_result = await agent.run(first_query)
        print(f"Agent: {first_result.text}")

        # Second conversation - still no thread provided, will create another new thread
        second_query = "What was the last city I asked about?"
        print(f"\nUser: {second_query}")
        second_result = await agent.run(second_query)
        print(f"Agent: {second_result.text}")
        print("Note: Each call creates a separate thread, so the agent doesn't remember previous context.\n")


async def example_with_thread_persistence() -> None:
    """Example showing thread persistence across multiple conversations."""
    print("=== Thread Persistence Example ===")
    print("Using the same thread across multiple conversations to maintain context.\n")

    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    async with (
        AzureCliCredential() as credential,
        ChatAgent(
            chat_client=AzureAIAgentClient(async_credential=credential),
            instructions="You are a helpful weather agent.",
            tools=get_weather,
        ) as agent,
    ):
        # Create a new thread that will be reused
        thread = agent.get_new_thread()

        # First conversation
        first_query = "What's the weather like in Tokyo?"
        print(f"User: {first_query}")
        first_result = await agent.run(first_query, thread=thread)
        print(f"Agent: {first_result.text}")

        # Second conversation using the same thread - maintains context
        second_query = "How about London?"
        print(f"\nUser: {second_query}")
        second_result = await agent.run(second_query, thread=thread)
        print(f"Agent: {second_result.text}")

        # Third conversation - agent should remember both previous cities
        third_query = "Which of the cities I asked about has better weather?"
        print(f"\nUser: {third_query}")
        third_result = await agent.run(third_query, thread=thread)
        print(f"Agent: {third_result.text}")
        print("Note: The agent remembers context from previous messages in the same thread.\n")


async def example_with_existing_thread_id() -> None:
    """Example showing how to work with an existing thread ID from the service."""
    print("=== Existing Thread ID Example ===")
    print("Using a specific thread ID to continue an existing conversation.\n")

    # First, create a conversation and capture the thread ID
    existing_thread_id = None

    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    async with (
        AzureCliCredential() as credential,
        ChatAgent(
            chat_client=AzureAIAgentClient(async_credential=credential),
            instructions="You are a helpful weather agent.",
            tools=get_weather,
        ) as agent,
    ):
        # Start a conversation and get the thread ID
        thread = agent.get_new_thread()
        first_query = "What's the weather in Paris?"
        print(f"User: {first_query}")
        first_result = await agent.run(first_query, thread=thread)
        print(f"Agent: {first_result.text}")

        # The thread ID is set after the first response
        existing_thread_id = thread.service_thread_id
        print(f"Thread ID: {existing_thread_id}")

    if existing_thread_id:
        print("\n--- Continuing with the same thread ID in a new agent instance ---")

        # Create a new agent instance but use the existing thread ID
        async with (
            AzureCliCredential() as credential,
            ChatAgent(
                chat_client=AzureAIAgentClient(thread_id=existing_thread_id, async_credential=credential),
                instructions="You are a helpful weather agent.",
                tools=get_weather,
            ) as agent,
        ):
            # Create a thread with the existing ID
            thread = AgentThread(service_thread_id=existing_thread_id)

            second_query = "What was the last city I asked about?"
            print(f"User: {second_query}")
            second_result = await agent.run(second_query, thread=thread)
            print(f"Agent: {second_result.text}")
            print("Note: The agent continues the conversation from the previous thread.\n")


async def main() -> None:
    print("=== Azure AI Chat Client Agent Thread Management Examples ===\n")

    await example_with_automatic_thread_creation()
    await example_with_thread_persistence()
    await example_with_existing_thread_id()


if __name__ == "__main__":
    asyncio.run(main())
