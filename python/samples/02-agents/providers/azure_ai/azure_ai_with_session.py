# Copyright (c) Microsoft. All rights reserved.

import asyncio
from random import randint
from typing import Annotated

from agent_framework import tool
from agent_framework.azure import AzureAIProjectAgentProvider
from azure.identity.aio import AzureCliCredential
from pydantic import Field

"""
Azure AI Agent with Session Management Example

This sample demonstrates session management with Azure AI Agent, showing
persistent conversation capabilities using service-managed sessions as well as storing messages in-memory.
"""


# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production
# See:
# samples/02-agents/tools/function_tool_with_approval.py
# samples/02-agents/tools/function_tool_with_approval_and_sessions.py.
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

    async with (
        AzureCliCredential() as credential,
        AzureAIProjectAgentProvider(credential=credential) as provider,
    ):
        agent = await provider.create_agent(
            name="BasicWeatherAgent",
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

    async with (
        AzureCliCredential() as credential,
        AzureAIProjectAgentProvider(credential=credential) as provider,
    ):
        agent = await provider.create_agent(
            name="BasicWeatherAgent",
            instructions="You are a helpful weather agent.",
            tools=get_weather,
        )

        # Create a new session that will be reused
        session = agent.create_session()

        # First conversation
        first_query = "What's the weather like in Tokyo?"
        print(f"User: {first_query}")
        first_result = await agent.run(first_query, session=session, options={"store": False})
        print(f"Agent: {first_result.text}")

        # Second conversation using the same session - maintains context
        second_query = "How about London?"
        print(f"\nUser: {second_query}")
        second_result = await agent.run(second_query, session=session, options={"store": False})
        print(f"Agent: {second_result.text}")

        # Third conversation - agent should remember both previous cities
        third_query = "Which of the cities I asked about has better weather?"
        print(f"\nUser: {third_query}")
        third_result = await agent.run(third_query, session=session, options={"store": False})
        print(f"Agent: {third_result.text}")
        print("Note: The agent remembers context from previous messages in the same session.\n")


async def example_with_existing_session_id() -> None:
    """
    Example showing how to work with an existing session ID from the service.
    In this example, messages are stored on the server.
    """
    print("=== Existing Session ID Example ===")

    # First, create a conversation and capture the session ID
    existing_session_id = None

    async with (
        AzureCliCredential() as credential,
        AzureAIProjectAgentProvider(credential=credential) as provider,
    ):
        agent = await provider.create_agent(
            name="BasicWeatherAgent",
            instructions="You are a helpful weather agent.",
            tools=get_weather,
        )

        # Start a conversation and get the session ID
        session = agent.create_session()

        first_query = "What's the weather in Paris?"
        print(f"User: {first_query}")
        first_result = await agent.run(first_query, session=session)
        print(f"Agent: {first_result.text}")

        # The session ID is set after the first response
        existing_session_id = session.service_session_id
        print(f"Session ID: {existing_session_id}")

        if existing_session_id:
            print("\n--- Continuing with the same session ID in a new agent instance ---")

            # Retrieve the same agent (reuses existing agent version on the service)
            second_agent = await provider.get_agent(
                name="BasicWeatherAgent",
                tools=get_weather,
            )

            # Attach the existing service session ID so conversation context is preserved
            session = second_agent.get_session(service_session_id=existing_session_id)

            second_query = "What was the last city I asked about?"
            print(f"User: {second_query}")
            second_result = await second_agent.run(second_query, session=session)
            print(f"Agent: {second_result.text}")
            print("Note: The agent continues the conversation from the previous session by using session ID.\n")


async def main() -> None:
    print("=== Azure AI Agent Session Management Examples ===\n")

    await example_with_automatic_session_creation()
    await example_with_session_persistence_in_memory()
    await example_with_existing_session_id()


if __name__ == "__main__":
    asyncio.run(main())
