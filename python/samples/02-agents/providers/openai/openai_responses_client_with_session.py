# Copyright (c) Microsoft. All rights reserved.

import asyncio
from random import randint
from typing import Annotated

from agent_framework import Agent, AgentSession, tool
from agent_framework.openai import OpenAIResponsesClient
from dotenv import load_dotenv
from pydantic import Field

# Load environment variables from .env file
load_dotenv()

"""
OpenAI Responses Client with Session Management Example

This sample demonstrates session management with OpenAI Responses Client, showing
persistent conversation context and simplified response handling.
"""


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
    """Example showing automatic session creation."""
    print("=== Automatic Session Creation Example ===")

    agent = Agent(
        client=OpenAIResponsesClient(),
        instructions="You are a helpful weather agent.",
        tools=get_weather,
    )

    # First conversation - no session provided, will be created automatically
    query1 = "What's the weather like in Seattle?"
    print(f"User: {query1}")
    result1 = await agent.run(query1)
    print(f"Agent: {result1.text}")

    # Second conversation - still no session provided, will create another new session
    query2 = "What was the last city I asked about?"
    print(f"\nUser: {query2}")
    result2 = await agent.run(query2)
    print(f"Agent: {result2.text}")
    print("Note: Each call creates a separate session, so the agent doesn't remember previous context.\n")


async def example_with_session_persistence_in_memory() -> None:
    """
    Example showing session persistence across multiple conversations.
    In this example, messages are stored in-memory.
    """
    print("=== Session Persistence Example (In-Memory) ===")

    agent = Agent(
        client=OpenAIResponsesClient(),
        instructions="You are a helpful weather agent.",
        tools=get_weather,
    )

    # Create a new session that will be reused
    session = agent.create_session()

    # First conversation
    query1 = "What's the weather like in Tokyo?"
    print(f"User: {query1}")
    result1 = await agent.run(query1, session=session, store=False)
    print(f"Agent: {result1.text}")

    # Second conversation using the same session - maintains context
    query2 = "How about London?"
    print(f"\nUser: {query2}")
    result2 = await agent.run(query2, session=session, store=False)
    print(f"Agent: {result2.text}")

    # Third conversation - agent should remember both previous cities
    query3 = "Which of the cities I asked about has better weather?"
    print(f"\nUser: {query3}")
    result3 = await agent.run(query3, session=session, store=False)
    print(f"Agent: {result3.text}")
    print("Note: The agent remembers context from previous messages in the same session.\n")


async def example_with_existing_session_id() -> None:
    """
    Example showing how to work with an existing session ID from the service.
    In this example, messages are stored on the server using OpenAI conversation state.
    """
    print("=== Existing Session ID Example ===")

    # First, create a conversation and capture the session ID
    existing_session_id = None

    agent = Agent(
        client=OpenAIResponsesClient(),
        instructions="You are a helpful weather agent.",
        tools=get_weather,
    )

    # Start a conversation and get the session ID
    session = agent.create_session()

    query1 = "What's the weather in Paris?"
    print(f"User: {query1}")
    result1 = await agent.run(query1, session=session)
    print(f"Agent: {result1.text}")

    # The session ID is set after the first response
    existing_session_id = session.service_session_id
    print(f"Session ID: {existing_session_id}")

    if existing_session_id:
        print("\n--- Continuing with the same session ID in a new agent instance ---")

        agent = Agent(
            client=OpenAIResponsesClient(),
            instructions="You are a helpful weather agent.",
            tools=get_weather,
        )

        # Create a session with the existing ID
        session = AgentSession(service_session_id=existing_session_id)

        query2 = "What was the last city I asked about?"
        print(f"User: {query2}")
        result2 = await agent.run(query2, session=session)
        print(f"Agent: {result2.text}")
        print("Note: The agent continues the conversation from the previous session by using session ID.\n")


async def main() -> None:
    print("=== OpenAI Response Client Agent Session Management Examples ===\n")

    await example_with_automatic_session_creation()
    await example_with_session_persistence_in_memory()
    await example_with_existing_session_id()


if __name__ == "__main__":
    asyncio.run(main())
