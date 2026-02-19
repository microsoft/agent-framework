# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import AgentSession
from agent_framework.azure import AzureAIAgentClient
from agent_framework.openai import OpenAIChatClient
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


async def suspend_resume_service_managed_session() -> None:
    """Demonstrates how to suspend and resume a service-managed session."""
    print("=== Suspend-Resume Service-Managed Session ===")

    # AzureAIAgentClient supports service-managed sessions.
    async with (
        AzureCliCredential() as credential,
        AzureAIAgentClient(credential=credential).as_agent(
            name="MemoryBot", instructions="You are a helpful assistant that remembers our conversation."
        ) as agent,
    ):
        # Start a new session for the agent conversation.
        session = agent.create_session()

        # Respond to user input.
        query = "Hello! My name is Alice and I love pizza."
        print(f"User: {query}")
        print(f"Agent: {await agent.run(query, session=session)}\n")

        # Serialize the session state, so it can be stored for later use.
        serialized_session = session.to_dict()

        # The session can now be saved to a database, file, or any other storage mechanism and loaded again later.
        print(f"Serialized session: {serialized_session}\n")

        # Deserialize the session state after loading from storage.
        resumed_session = AgentSession.from_dict(serialized_session)

        # Respond to user input.
        query = "What do you remember about me?"
        print(f"User: {query}")
        print(f"Agent: {await agent.run(query, session=resumed_session)}\n")


async def suspend_resume_in_memory_session() -> None:
    """Demonstrates how to suspend and resume an in-memory session."""
    print("=== Suspend-Resume In-Memory Session ===")

    # OpenAI Chat Client is used as an example here,
    # other chat clients can be used as well.
    agent = OpenAIChatClient().as_agent(
        name="MemoryBot", instructions="You are a helpful assistant that remembers our conversation."
    )

    # Start a new session for the agent conversation.
    session = agent.create_session()

    # Respond to user input.
    query = "Hello! My name is Alice and I love pizza."
    print(f"User: {query}")
    print(f"Agent: {await agent.run(query, session=session)}\n")

    # Serialize the session state, so it can be stored for later use.
    serialized_session = session.to_dict()

    # The session can now be saved to a database, file, or any other storage mechanism and loaded again later.
    print(f"Serialized session: {serialized_session}\n")

    # Deserialize the session state after loading from storage.
    resumed_session = AgentSession.from_dict(serialized_session)

    # Respond to user input.
    query = "What do you remember about me?"
    print(f"User: {query}")
    print(f"Agent: {await agent.run(query, session=resumed_session)}\n")


async def main() -> None:
    print("=== Suspend-Resume Session Examples ===")
    await suspend_resume_service_managed_session()
    await suspend_resume_in_memory_session()


if __name__ == "__main__":
    asyncio.run(main())
