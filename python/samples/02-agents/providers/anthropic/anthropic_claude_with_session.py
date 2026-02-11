# Copyright (c) Microsoft. All rights reserved.

"""
Claude Agent with Session Management

This sample demonstrates session management with ClaudeAgent, showing
persistent conversation capabilities. Sessions are automatically persisted
by the Claude Code CLI.
"""

import asyncio
from random import randint
from typing import Annotated

from agent_framework import tool
from agent_framework_claude import ClaudeAgent
from pydantic import Field


@tool
def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def example_with_automatic_session_creation() -> None:
    """Each agent instance creates a new session."""
    print("=== Automatic Session Creation Example ===")

    # First agent - first session
    agent1 = ClaudeAgent(
        instructions="You are a helpful weather agent.",
        tools=[get_weather],
    )

    async with agent1:
        query1 = "What's the weather like in Seattle?"
        print(f"User: {query1}")
        result1 = await agent1.run(query1)
        print(f"Agent: {result1.text}")

    # Second agent - new session, no memory of previous conversation
    agent2 = ClaudeAgent(
        instructions="You are a helpful weather agent.",
        tools=[get_weather],
    )

    async with agent2:
        query2 = "What was the last city I asked about?"
        print(f"\nUser: {query2}")
        result2 = await agent2.run(query2)
        print(f"Agent: {result2.text}")
        print("Note: Each agent instance creates a separate session, so the agent doesn't remember previous context.\n")


async def example_with_session_persistence() -> None:
    """Reuse session via thread object for multi-turn conversations."""
    print("=== Session Persistence Example ===")

    agent = ClaudeAgent(
        instructions="You are a helpful weather agent.",
        tools=[get_weather],
    )

    async with agent:
        # Create a thread to maintain conversation context
        thread = agent.get_new_thread()

        # First query
        query1 = "What's the weather like in Tokyo?"
        print(f"User: {query1}")
        result1 = await agent.run(query1, thread=thread)
        print(f"Agent: {result1.text}")

        # Second query - using same thread maintains context
        query2 = "How about London?"
        print(f"\nUser: {query2}")
        result2 = await agent.run(query2, thread=thread)
        print(f"Agent: {result2.text}")

        # Third query - agent should remember both previous cities
        query3 = "Which of the cities I asked about has better weather?"
        print(f"\nUser: {query3}")
        result3 = await agent.run(query3, thread=thread)
        print(f"Agent: {result3.text}")
        print("Note: The agent remembers context from previous messages in the same session.\n")


async def example_with_existing_session_id() -> None:
    """Resume session in new agent instance using service_thread_id."""
    print("=== Existing Session ID Example ===")

    existing_session_id = None

    # First agent instance - start a conversation
    agent1 = ClaudeAgent(
        instructions="You are a helpful weather agent.",
        tools=[get_weather],
    )

    async with agent1:
        thread = agent1.get_new_thread()

        query1 = "What's the weather in Paris?"
        print(f"User: {query1}")
        result1 = await agent1.run(query1, thread=thread)
        print(f"Agent: {result1.text}")

        # Capture the session ID for later use
        existing_session_id = thread.service_thread_id
        print(f"Session ID: {existing_session_id}")

    if existing_session_id:
        print("\n--- Continuing with the same session ID in a new agent instance ---")

        # Second agent instance - resume the conversation
        agent2 = ClaudeAgent(
            instructions="You are a helpful weather agent.",
            tools=[get_weather],
        )

        async with agent2:
            # Create thread with existing session ID
            thread = agent2.get_new_thread(service_thread_id=existing_session_id)

            query2 = "What was the last city I asked about?"
            print(f"User: {query2}")
            result2 = await agent2.run(query2, thread=thread)
            print(f"Agent: {result2.text}")
            print("Note: The agent continues the conversation using the session ID.\n")


async def main() -> None:
    print("=== Claude Agent Session Management Examples ===\n")

    await example_with_automatic_session_creation()
    await example_with_session_persistence()
    await example_with_existing_session_id()


if __name__ == "__main__":
    asyncio.run(main())
