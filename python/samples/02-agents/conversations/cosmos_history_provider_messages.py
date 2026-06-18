# Copyright (c) Microsoft. All rights reserved.
# ruff: noqa: T201

import asyncio
import os

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework_azure_cosmos import CosmosHistoryProvider
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file.
load_dotenv()

"""
This sample demonstrates direct message history operations using
CosmosHistoryProvider — retrieving, displaying, and clearing stored messages.

Key components:
- get_messages(session_id): Retrieve all stored messages as a chat transcript
- clear(session_id): Delete all messages for a session (e.g., GDPR compliance)
- Verifying that history is empty after clearing
- Running a new conversation in the same session after clearing

Environment variables:
  FOUNDRY_PROJECT_ENDPOINT
  FOUNDRY_MODEL
  AZURE_COSMOS_ENDPOINT
  AZURE_COSMOS_DATABASE_NAME
  AZURE_COSMOS_CONTAINER_NAME
Optional:
  AZURE_COSMOS_KEY
"""


async def main() -> None:
    """Run the messages history sample."""
    project_endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT")
    model = os.getenv("FOUNDRY_MODEL")
    cosmos_endpoint = os.getenv("AZURE_COSMOS_ENDPOINT")
    cosmos_database_name = os.getenv("AZURE_COSMOS_DATABASE_NAME")
    cosmos_container_name = os.getenv("AZURE_COSMOS_CONTAINER_NAME")
    cosmos_key = os.getenv("AZURE_COSMOS_KEY")

    if (
        not project_endpoint
        or not model
        or not cosmos_endpoint
        or not cosmos_database_name
        or not cosmos_container_name
    ):
        print(
            "Please set FOUNDRY_PROJECT_ENDPOINT, FOUNDRY_MODEL, "
            "AZURE_COSMOS_ENDPOINT, AZURE_COSMOS_DATABASE_NAME, and AZURE_COSMOS_CONTAINER_NAME."
        )
        return

    async with (
        AzureCliCredential() as credential,
        CosmosHistoryProvider(
            endpoint=cosmos_endpoint,
            database_name=cosmos_database_name,
            container_name=cosmos_container_name,
            credential=cosmos_key or credential,
        ) as history_provider,
        Agent(
            client=FoundryChatClient(
                project_endpoint=project_endpoint,
                model=model,
                credential=credential,
            ),
            name="HistoryAgent",
            instructions="You are a helpful assistant that remembers prior turns.",
            context_providers=[history_provider],
            default_options={"store": False},
        ) as agent,
    ):
        session = agent.create_session()
        session_id = session.session_id

        # 1. Have a multi-turn conversation.
        print("=== Building a conversation ===\n")

        queries = [
            "Hi! My favorite programming language is Python.",
            "I also enjoy hiking in the mountains on weekends.",
            "What do you know about me so far?",
        ]
        for query in queries:
            response = await agent.run(query, session=session)
            print(f"User:      {query}")
            print(f"Assistant: {response.text}\n")

        # 2. Retrieve and display the full message history as a transcript.
        print("=== Chat transcript from Cosmos DB ===\n")

        messages = await history_provider.get_messages(session_id)
        print(f"Total messages stored: {len(messages)}\n")
        for i, msg in enumerate(messages, 1):
            print(f"  {i}. [{msg.role}] {msg.text[:100]}")

        # 3. Clear the session history.
        print("\n=== Clearing session history ===\n")

        await history_provider.clear(session_id)
        print(f"Cleared all messages for session: {session_id}")

        # 4. Verify history is empty.
        remaining = await history_provider.get_messages(session_id)
        print(f"Messages after clear: {len(remaining)}")

        # 5. Start a fresh conversation in the same session — agent has no memory.
        print("\n=== Fresh conversation (same session, no memory) ===\n")

        response = await agent.run("What do you know about me?", session=session)
        print("User:      What do you know about me?")
        print(f"Assistant: {response.text}")


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:
=== Building a conversation ===

User:      Hi! My favorite programming language is Python.
Assistant: That's great! Python is a wonderful language. What do you like most about it?

User:      I also enjoy hiking in the mountains on weekends.
Assistant: Hiking sounds lovely! Do you have a favorite trail or mountain range?

User:      What do you know about me so far?
Assistant: You love Python as your favorite programming language and enjoy hiking in the mountains on weekends.

=== Chat transcript from Cosmos DB ===

Total messages stored: 6

  1. [user] Hi! My favorite programming language is Python.
  2. [assistant] That's great! Python is a wonderful language. What do you like most about it?
  3. [user] I also enjoy hiking in the mountains on weekends.
  4. [assistant] Hiking sounds lovely! Do you have a favorite trail or mountain range?
  5. [user] What do you know about me so far?
  6. [assistant] You love Python as your favorite programming language and enjoy hiking ...

=== Clearing session history ===

Cleared all messages for session: <session-uuid>
Messages after clear: 0

=== Fresh conversation (same session, no memory) ===

User:      What do you know about me?
Assistant: I don't have any information about you yet. Feel free to share anything you'd like!
"""
