# Copyright (c) Microsoft. All rights reserved.

"""
GitHub Copilot Agent with Session Management

This sample demonstrates session management with GitHubCopilotAgent, showing
persistent conversation capabilities. Sessions are automatically persisted
server-side by the Copilot CLI.
"""

import asyncio
from random import randint
from typing import Annotated

from agent_framework import tool
from agent_framework.github import GitHubCopilotAgent
from pydantic import Field


# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production;
# see samples/02-agents/tools/function_tool_with_approval.py
# and samples/02-agents/tools/function_tool_with_approval_and_sessions.py.
@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def example_with_automatic_session_creation() -> None:
    """Each run() without thread creates a new session."""
    print("=== Automatic Session Creation Example ===")

    agent = GitHubCopilotAgent(
        instructions="You are a helpful weather agent.",
        tools=[get_weather],
    )

    async with agent:
        # First query - creates a new session
        query1 = "What's the weather like in Seattle?"
        print(f"User: {query1}")
        result1 = await agent.run(query1)
        print(f"Agent: {result1}")

        # Second query - without thread, creates another new session
        query2 = "What was the last city I asked about?"
        print(f"\nUser: {query2}")
        result2 = await agent.run(query2)
        print(f"Agent: {result2}")
        print("Note: Each call creates a separate session, so the agent doesn't remember previous context.\n")


async def example_with_session_persistence() -> None:
    """Reuse session via thread object for multi-turn conversations."""
    print("=== Session Persistence Example ===")

    agent = GitHubCopilotAgent(
        instructions="You are a helpful weather agent.",
        tools=[get_weather],
    )

    async with agent:
        # Create a session to maintain conversation context
        session = agent.create_session()

        # First query
        query1 = "What's the weather like in Tokyo?"
        print(f"User: {query1}")
        result1 = await agent.run(query1, session=session)
        print(f"Agent: {result1}")

        # Second query - using same thread maintains context
        query2 = "How about London?"
        print(f"\nUser: {query2}")
        result2 = await agent.run(query2, session=session)
        print(f"Agent: {result2}")

        # Third query - agent should remember both previous cities
        query3 = "Which of the cities I asked about has better weather?"
        print(f"\nUser: {query3}")
        result3 = await agent.run(query3, session=session)
        print(f"Agent: {result3}")
        print("Note: The agent remembers context from previous messages in the same session.\n")


async def example_with_existing_session_id() -> None:
    """Resume session in new agent instance using service_session_id."""
    print("=== Existing Session ID Example ===")

    existing_session_id = None

    # First agent instance - start a conversation
    agent1 = GitHubCopilotAgent(
        instructions="You are a helpful weather agent.",
        tools=[get_weather],
    )

    async with agent1:
        session = agent1.create_session()

        query1 = "What's the weather in Paris?"
        print(f"User: {query1}")
        result1 = await agent1.run(query1, session=session)
        print(f"Agent: {result1}")

        # Capture the session ID for later use
        existing_session_id = session.service_session_id
        print(f"Session ID: {existing_session_id}")

    if existing_session_id:
        print("\n--- Continuing with the same session ID in a new agent instance ---")

        # Second agent instance - resume the conversation
        agent2 = GitHubCopilotAgent(
            instructions="You are a helpful weather agent.",
            tools=[get_weather],
        )

        async with agent2:
            # Get session with existing session ID
            session = agent2.get_session(service_session_id=existing_session_id)

            query2 = "What was the last city I asked about?"
            print(f"User: {query2}")
            result2 = await agent2.run(query2, session=session)
            print(f"Agent: {result2}")
            print("Note: The agent continues the conversation using the session ID.\n")


async def main() -> None:
    print("=== GitHub Copilot Agent Session Management Examples ===\n")

    await example_with_automatic_session_creation()
    await example_with_session_persistence()
    await example_with_existing_session_id()


if __name__ == "__main__":
    asyncio.run(main())
