# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import Agent, tool
from agent_framework.foundry import FoundryChatClient
from agent_framework.mem0 import Mem0ContextProvider
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production;
# see samples/02-agents/tools/function_tool_with_approval.py
# and samples/02-agents/tools/function_tool_with_approval_and_sessions.py.
@tool(approval_mode="never_require")
def get_user_preferences(user_id: str) -> str:
    """Mock function to get user preferences."""

    preferences = {
        "user123": "Prefers concise responses and technical details",
        "user456": "Likes detailed explanations with examples",
    }
    return preferences.get(user_id, "No specific preferences found")


async def example_user_scoped_memory() -> None:
    """Example 1: User-scoped memory (memories shared across all sessions for the same user)."""
    print("1. User-Scoped Memory Example:")
    print("-" * 40)

    user_id = "user123"

    async with (
        AzureCliCredential() as credential,
        Agent(
            client=FoundryChatClient(credential=credential),
            name="UserMemoryAssistant",
            instructions="You are an assistant that remembers user preferences across conversations.",
            tools=get_user_preferences,
            context_providers=[
                Mem0ContextProvider(
                    source_id="mem0",
                    user_id=user_id,
                )
            ],
        ) as user_agent,
    ):
        # Store some preferences
        query = "Remember that I prefer technical responses with code examples when discussing programming."
        print(f"User: {query}")
        result = await user_agent.run(query)
        print(f"Agent: {result}\n")

        # Create a new session - memories should still be accessible via user_id scoping
        new_session = user_agent.create_session()
        query = "What do you know about my preferences?"
        print(f"User (new session): {query}")
        result = await user_agent.run(query, session=new_session)
        print(f"Agent: {result}\n")


async def example_agent_scoped_memory() -> None:
    """Example 2: Agent-scoped memory (memories isolated per agent_id).

    Note: Use different agent_id values to isolate memories between different
    agent personas, even when the user_id is the same.
    """
    print("2. Agent-Scoped Memory Example:")
    print("-" * 40)

    user_id = "user123"

    async with (
        AzureCliCredential() as credential,
        Agent(
            client=FoundryChatClient(credential=credential),
            name="ScopedMemoryAssistant",
            instructions="You are an assistant with agent-scoped memory.",
            tools=get_user_preferences,
            context_providers=[
                Mem0ContextProvider(
                    source_id="mem0",
                    user_id=user_id,
                    agent_id="scoped_assistant",
                )
            ],
        ) as scoped_agent,
    ):
        # Store some information
        query = "Remember that for this conversation, I'm working on a Python project about data analysis."
        print(f"User: {query}")
        result = await scoped_agent.run(query)
        print(f"Agent: {result}\n")

        # Test memory retrieval
        query = "What project am I working on?"
        print(f"User: {query}")
        result = await scoped_agent.run(query)
        print(f"Agent: {result}\n")

        # Store more information
        query = "Also remember that I prefer using pandas and matplotlib for this project."
        print(f"User: {query}")
        result = await scoped_agent.run(query)
        print(f"Agent: {result}\n")

        # Test comprehensive memory retrieval
        query = "What do you know about my current project and preferences?"
        print(f"User: {query}")
        result = await scoped_agent.run(query)
        print(f"Agent: {result}\n")


async def example_multiple_agents() -> None:
    """Example 3: Multiple agents with different memory configurations."""
    print("3. Multiple Agents with Different Memory Configurations:")
    print("-" * 40)

    agent_id_1 = "agent_personal"
    agent_id_2 = "agent_work"

    async with (
        AzureCliCredential() as credential,
        Agent(
            client=FoundryChatClient(credential=credential),
            name="PersonalAssistant",
            instructions="You are a personal assistant that helps with personal tasks.",
            context_providers=[
                Mem0ContextProvider(
                    source_id="mem0",
                    agent_id=agent_id_1,
                )
            ],
        ) as personal_agent,
        Agent(
            client=FoundryChatClient(credential=credential),
            name="WorkAssistant",
            instructions="You are a work assistant that helps with professional tasks.",
            context_providers=[
                Mem0ContextProvider(
                    source_id="mem0",
                    agent_id=agent_id_2,
                )
            ],
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
    """Run all Mem0 memory management examples."""
    print("=== Mem0 Memory Management Example ===\n")

    await example_user_scoped_memory()
    await example_agent_scoped_memory()
    await example_multiple_agents()


if __name__ == "__main__":
    asyncio.run(main())
