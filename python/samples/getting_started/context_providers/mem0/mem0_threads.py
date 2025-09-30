# Copyright (c) Microsoft. All rights reserved.

import asyncio
import uuid

from agent_framework.azure import AzureAIAgentClient
from agent_framework.mem0 import Mem0Provider
from azure.identity.aio import AzureCliCredential


def get_user_preferences(user_id: str) -> str:
    """Mock function to get user preferences."""
    preferences = {
        "user123": "Prefers concise responses and technical details",
        "user456": "Likes detailed explanations with examples",
    }
    return preferences.get(user_id, "No specific preferences found")


async def example_global_thread_scope() -> None:
    """Example 1: Global thread_id scope (memories shared across all operations)."""
    print("1. Global Thread Scope Example:")
    print("-" * 40)

    global_thread_id = str(uuid.uuid4())
    user_id = "user123"

    async with (
        AzureCliCredential() as credential,
        AzureAIAgentClient(async_credential=credential).create_agent(
            name="GlobalMemoryAssistant",
            instructions="You are an assistant that remembers user preferences across conversations.",
            tools=get_user_preferences,
            context_providers=Mem0Provider(
                user_id=user_id,
                thread_id=global_thread_id,
                scope_to_per_operation_thread_id=False,  # Share memories across all threads
            ),
        ) as global_agent,
    ):
        # Store some preferences in the global scope
        query = "Remember that I prefer technical responses with code examples when discussing programming."
        print(f"User: {query}")
        result = await global_agent.run(query)
        print(f"Agent: {result}\n")

        # Create a new thread - but memories should still be accessible due to global scope
        new_thread = global_agent.get_new_thread()
        query = "What do you know about my preferences?"
        print(f"User (new thread): {query}")
        result = await global_agent.run(query, thread=new_thread)
        print(f"Agent: {result}\n")


async def example_per_operation_thread_scope() -> None:
    """Example 2: Per-operation thread scope (memories isolated per thread).

    Note: When scope_to_per_operation_thread_id=True, the provider is bound to a single thread
    throughout its lifetime. Use the same thread object for all operations with that provider.
    """
    print("2. Per-Operation Thread Scope Example:")
    print("-" * 40)

    user_id = "user123"

    async with (
        AzureCliCredential() as credential,
        AzureAIAgentClient(async_credential=credential).create_agent(
            name="ScopedMemoryAssistant",
            instructions="You are an assistant with thread-scoped memory.",
            tools=get_user_preferences,
            context_providers=Mem0Provider(
                user_id=user_id,
                scope_to_per_operation_thread_id=True,  # Isolate memories per thread
            ),
        ) as scoped_agent,
    ):
        # Create a specific thread for this scoped provider
        dedicated_thread = scoped_agent.get_new_thread()

        # Store some information in the dedicated thread
        query = "Remember that for this conversation, I'm working on a Python project about data analysis."
        print(f"User (dedicated thread): {query}")
        result = await scoped_agent.run(query, thread=dedicated_thread)
        print(f"Agent: {result}\n")

        # Test memory retrieval in the same dedicated thread
        query = "What project am I working on?"
        print(f"User (same dedicated thread): {query}")
        result = await scoped_agent.run(query, thread=dedicated_thread)
        print(f"Agent: {result}\n")

        # Store more information in the same thread
        query = "Also remember that I prefer using pandas and matplotlib for this project."
        print(f"User (same dedicated thread): {query}")
        result = await scoped_agent.run(query, thread=dedicated_thread)
        print(f"Agent: {result}\n")

        # Test comprehensive memory retrieval
        query = "What do you know about my current project and preferences?"
        print(f"User (same dedicated thread): {query}")
        result = await scoped_agent.run(query, thread=dedicated_thread)
        print(f"Agent: {result}\n")


async def example_multiple_agents() -> None:
    """Example 3: Multiple agents with different thread configurations."""
    print("3. Multiple Agents with Different Thread Configurations:")
    print("-" * 40)

    agent_id_1 = "agent_personal"
    agent_id_2 = "agent_work"

    async with (
        AzureCliCredential() as credential,
        AzureAIAgentClient(async_credential=credential).create_agent(
            name="PersonalAssistant",
            instructions="You are a personal assistant that helps with personal tasks.",
            context_providers=Mem0Provider(
                agent_id=agent_id_1,
            ),
        ) as personal_agent,
        AzureAIAgentClient(async_credential=credential).create_agent(
            name="WorkAssistant",
            instructions="You are a work assistant that helps with professional tasks.",
            context_providers=Mem0Provider(
                agent_id=agent_id_2,
            ),
        ) as work_agent,
    ):
        # Store personal information
        query = "Remember that I like to exercise at 6 AM and prefer outdoor activities."
        print(f"User to Personal Agent: {query}")
        result = await personal_agent.run(query)
        print(f"Personal Agent: {result}\n")

        # Store work information
        query = "Remember that I have team meetings every Tuesday at 2 PM."
        print(f"User to Work Agent: {query}")
        result = await work_agent.run(query)
        print(f"Work Agent: {result}\n")

        # Test memory isolation
        query = "What do you know about my schedule?"
        print(f"User to Personal Agent: {query}")
        result = await personal_agent.run(query)
        print(f"Personal Agent: {result}\n")

        print(f"User to Work Agent: {query}")
        result = await work_agent.run(query)
        print(f"Work Agent: {result}\n")


async def main() -> None:
    """Run all Mem0 thread management examples."""
    print("=== Mem0 Thread Management Example ===\n")

    await example_global_thread_scope()
    await example_per_operation_thread_scope()
    await example_multiple_agents()


if __name__ == "__main__":
    asyncio.run(main())
