# Copyright (c) Microsoft. All rights reserved.

import asyncio
from random import randint
from typing import Annotated

from agent_framework import AgentSession, tool
from agent_framework.azure import AzureAIAgentsProvider
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv
from pydantic import Field

# Load environment variables from .env file
load_dotenv()

"""
Azure AI Agent with Session Management Example

This sample demonstrates session management with Azure AI Agents, comparing
automatic session creation with explicit session management for persistent context.
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

    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    async with (
        AzureCliCredential() as credential,
        AzureAIAgentsProvider(credential=credential) as provider,
    ):
        agent = await provider.create_agent(
            name="WeatherAgent",
            instructions="You are a helpful weather agent.",
            tools=get_weather,
        )

        # First conversation - no session provided, will be created automatically
        first_query = "What's the weather like in Seattle?"
        print(f"User: {first_query}")
        first_result = await agent.run(first_query)
        print(f"Agent: {first_result.text}")

        # Second conversation - still no session provided, will create another new session
        second_query = "What was the last city I asked about?"
        print(f"\nUser: {second_query}")
        second_result = await agent.run(second_query)
        print(f"Agent: {second_result.text}")
        print("Note: Each call creates a separate session, so the agent doesn't remember previous context.\n")


async def example_with_session_persistence() -> None:
    """Example showing session persistence across multiple conversations."""
    print("=== Session Persistence Example ===")
    print("Using the same session across multiple conversations to maintain context.\n")

    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    async with (
        AzureCliCredential() as credential,
        AzureAIAgentsProvider(credential=credential) as provider,
    ):
        agent = await provider.create_agent(
            name="WeatherAgent",
            instructions="You are a helpful weather agent.",
            tools=get_weather,
        )

        # Create a new session that will be reused
        session = agent.create_session()

        # First conversation
        first_query = "What's the weather like in Tokyo?"
        print(f"User: {first_query}")
        first_result = await agent.run(first_query, session=session)
        print(f"Agent: {first_result.text}")

        # Second conversation using the same session - maintains context
        second_query = "How about London?"
        print(f"\nUser: {second_query}")
        second_result = await agent.run(second_query, session=session)
        print(f"Agent: {second_result.text}")

        # Third conversation - agent should remember both previous cities
        third_query = "Which of the cities I asked about has better weather?"
        print(f"\nUser: {third_query}")
        third_result = await agent.run(third_query, session=session)
        print(f"Agent: {third_result.text}")
        print("Note: The agent remembers context from previous messages in the same session.\n")


async def example_with_existing_session_id() -> None:
    """Example showing how to work with an existing session ID from the service."""
    print("=== Existing Session ID Example ===")
    print("Using a specific session ID to continue an existing conversation.\n")

    # First, create a conversation and capture the session ID
    existing_session_id = None

    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    async with (
        AzureCliCredential() as credential,
        AzureAIAgentsProvider(credential=credential) as provider,
    ):
        agent = await provider.create_agent(
            name="WeatherAgent",
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

        # Create a new provider and agent but use the existing session ID
        async with (
            AzureCliCredential() as credential,
            AzureAIAgentsProvider(credential=credential) as provider,
        ):
            agent = await provider.create_agent(
                name="WeatherAgent",
                instructions="You are a helpful weather agent.",
                tools=get_weather,
            )

            # Create a session with the existing ID
            session = AgentSession(service_session_id=existing_session_id)

            second_query = "What was the last city I asked about?"
            print(f"User: {second_query}")
            second_result = await agent.run(second_query, session=session)
            print(f"Agent: {second_result.text}")
            print("Note: The agent continues the conversation from the previous session.\n")


async def main() -> None:
    print("=== Azure AI Chat Client Agent Session Management Examples ===\n")

    await example_with_automatic_session_creation()
    await example_with_session_persistence()
    await example_with_existing_session_id()


if __name__ == "__main__":
    asyncio.run(main())
