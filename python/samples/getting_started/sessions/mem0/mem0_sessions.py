# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import tool
from agent_framework.azure import AzureAIAgentClient
from agent_framework.mem0 import Mem0ContextProvider
from azure.identity.aio import AzureCliCredential


# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production; see samples/02-agents/tools/function_tool_with_approval.py and samples/02-agents/tools/function_tool_with_approval_and_sessions.py.
@tool(approval_mode="never_require")
def get_user_preferences(user_id: str) -> str:
    """Mock function to get user preferences."""
    preferences = {
        "user123": "Prefers concise responses and technical details",
        "user456": "Likes detailed explanations with examples",
    }
    return preferences.get(user_id, "No specific preferences found")


async def example_cross_session_memory() -> None:
    """Example 1: Cross-session memory (memories shared across all sessions for a user)."""
    print("1. Cross-Session Memory Example:")
    print("-" * 40)

    user_id = "user123"

    async with (
        AzureCliCredential() as credential,
        AzureAIAgentClient(credential=credential).as_agent(
            name="MemoryAssistant",
            instructions="You are an assistant that remembers user preferences across conversations.",
            tools=get_user_preferences,
            context_providers=[Mem0ContextProvider(user_id=user_id)],
        ) as agent,
    ):
        # Store some preferences
        query = "Remember that I prefer technical responses with code examples when discussing programming."
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result}\n")

        # Mem0 processes and indexes memories asynchronously.
        print("Waiting for memories to be processed...")
        await asyncio.sleep(12)

        # Create a new session - memories should still be accessible
        # because Mem0 scopes by user_id, not session
        new_session = agent.create_session()
        query = "What do you know about my preferences?"
        print(f"User (new session): {query}")
        result = await agent.run(query, session=new_session)
        print(f"Agent: {result}\n")


async def example_agent_scoped_memory() -> None:
    """Example 2: Agent-scoped memory (memories isolated per agent)."""
    print("2. Agent-Scoped Memory Example:")
    print("-" * 40)

    async with (
        AzureCliCredential() as credential,
        AzureAIAgentClient(credential=credential).as_agent(
            name="PersonalAssistant",
            instructions="You are a personal assistant that helps with personal tasks.",
            context_providers=[Mem0ContextProvider(agent_id="agent_personal")],
        ) as personal_agent,
        AzureAIAgentClient(credential=credential).as_agent(
            name="WorkAssistant",
            instructions="You are a work assistant that helps with professional tasks.",
            context_providers=[Mem0ContextProvider(agent_id="agent_work")],
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

        # Mem0 processes and indexes memories asynchronously.
        print("Waiting for memories to be processed...")
        await asyncio.sleep(12)

        # Test memory isolation - each agent should only recall its own memories
        query = "What do you know about my schedule?"
        print(f"User to Personal Agent: {query}")
        result = await personal_agent.run(query)
        print(f"Personal Agent: {result}\n")

        print(f"User to Work Agent: {query}")
        result = await work_agent.run(query)
        print(f"Work Agent: {result}\n")


async def main() -> None:
    """Run all Mem0 session management examples."""
    print("=== Mem0 Session Management Example ===\n")

    await example_cross_session_memory()
    await example_agent_scoped_memory()


if __name__ == "__main__":
    asyncio.run(main())
