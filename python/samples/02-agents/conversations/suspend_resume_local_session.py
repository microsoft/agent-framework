# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import Agent, AgentSession, InMemoryHistoryProvider
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
Session Suspend and Resume Example

This sample demonstrates how to suspend and resume conversation sessions, comparing
service-managed sessions (Azure AI) with in-memory sessions (OpenAI) for persistent
conversation state across sessions.
"""


def get_weather(location: str) -> str:
    """Mock weather lookup function."""
    return f"The weather in {location} is sunny with a high of 25°C."


async def main() -> None:
    """Demonstrates how to suspend and resume a service-managed session."""
    print("=== Suspend-Resume Service-Managed Session ===")

    async with (
        AzureCliCredential() as credential,
        Agent(
            client=FoundryChatClient(credential=credential),
            name="MemoryBot",
            instructions="You are a helpful assistant that remembers our conversation.",
            default_options={"store": False},  # Store messages in the session by default to enable resuming later.
            context_providers=[InMemoryHistoryProvider()],
            tools=[get_weather],
        ) as agent,
    ):
        # Start a new session for the agent conversation.
        session = agent.create_session()

        # Respond to user input.
        query = "Hello! What's the weather in Amsterdam?."
        print(f"User: {query}")
        print(f"Agent: {await agent.run(query, session=session)}\n")

        # Serialize the session state, so it can be stored for later use.
        serialized_session = session.to_dict()

        # The session can now be saved to a database, file, or any other storage mechanism and loaded again later.
        print(f"Serialized session: {serialized_session}\n")

        # Deserialize the session state after loading from storage.
        resumed_session = AgentSession.from_dict(serialized_session)

        # Respond to user input.
        query = "And what about Tokyo?"
        print(f"User: {query}")
        print(f"Agent: {await agent.run(query, session=resumed_session)}\n")


if __name__ == "__main__":
    asyncio.run(main())
