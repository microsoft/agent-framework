# Copyright (c) Microsoft. All rights reserved.

import asyncio
from random import randint
from typing import Annotated

from agent_framework import Agent, AgentSession, InMemoryHistoryProvider, tool
from agent_framework.openai import OpenAIChatClient
from pydantic import Field

"""
OpenAI Chat Client with Session Management Example

This sample demonstrates session management with OpenAI Chat Client, showing
conversation sessions and message history preservation across interactions.
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
    """Example showing automatic session creation (service-managed session)."""
    print("=== Automatic Session Creation Example ===")

    agent = Agent(
        client=OpenAIChatClient(),
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


async def example_with_session_persistence() -> None:
    """Example showing session persistence across multiple conversations."""
    print("=== Session Persistence Example ===")
    print("Using the same session across multiple conversations to maintain context.\n")

    agent = Agent(
        client=OpenAIChatClient(),
        instructions="You are a helpful weather agent.",
        tools=get_weather,
    )

    # Create a new session that will be reused
    session = agent.create_session()

    # First conversation
    query1 = "What's the weather like in Tokyo?"
    print(f"User: {query1}")
    result1 = await agent.run(query1, session=session)
    print(f"Agent: {result1.text}")

    # Second conversation using the same session - maintains context
    query2 = "How about London?"
    print(f"\nUser: {query2}")
    result2 = await agent.run(query2, session=session)
    print(f"Agent: {result2.text}")

    # Third conversation - agent should remember both previous cities
    query3 = "Which of the cities I asked about has better weather?"
    print(f"\nUser: {query3}")
    result3 = await agent.run(query3, session=session)
    print(f"Agent: {result3.text}")
    print("Note: The agent remembers context from previous messages in the same session.\n")


async def example_with_existing_session_messages() -> None:
    """Example showing how to work with existing session messages for OpenAI."""
    print("=== Existing Session Messages Example ===")

    agent = Agent(
        client=OpenAIChatClient(),
        instructions="You are a helpful weather agent.",
        tools=get_weather,
    )

    # Start a conversation and build up message history
    session = agent.create_session()

    query1 = "What's the weather in Paris?"
    print(f"User: {query1}")
    result1 = await agent.run(query1, session=session)
    print(f"Agent: {result1.text}")

    # The session now contains the conversation history in state
    memory_state = session.state.get(InMemoryHistoryProvider.DEFAULT_SOURCE_ID, {})
    messages = memory_state.get("messages", [])
    if messages:
        print(f"Session contains {len(messages)} messages")

    print("\n--- Continuing with the same session in a new agent instance ---")

    # Create a new agent instance but use the existing session with its message history
    new_agent = Agent(
        client=OpenAIChatClient(),
        instructions="You are a helpful weather agent.",
        tools=get_weather,
    )

    # Use the same session object which contains the conversation history
    query2 = "What was the last city I asked about?"
    print(f"User: {query2}")
    result2 = await new_agent.run(query2, session=session)
    print(f"Agent: {result2.text}")
    print("Note: The agent continues the conversation using the local message history.\n")

    print("\n--- Alternative: Creating a new session from existing messages ---")

    new_session = AgentSession()

    query3 = "How does the Paris weather compare to London?"
    print(f"User: {query3}")
    result3 = await new_agent.run(query3, session=new_session)
    print(f"Agent: {result3.text}")
    print("Note: This creates a new session with the same conversation history.\n")


async def main() -> None:
    print("=== OpenAI Chat Client Agent Session Management Examples ===\n")

    await example_with_automatic_session_creation()
    await example_with_session_persistence()
    await example_with_existing_session_messages()


if __name__ == "__main__":
    asyncio.run(main())
