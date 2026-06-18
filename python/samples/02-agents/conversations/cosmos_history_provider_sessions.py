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
This sample demonstrates multi-session and multi-tenant management using
CosmosHistoryProvider. Each tenant (user) gets isolated conversation sessions
stored in the same Cosmos DB container, partitioned by session_id.

Key components:
- Per-tenant session isolation using prefixed session IDs
- list_sessions(): Enumerate all stored sessions across tenants
- Switching between sessions for different users
- Resuming a specific user's session — verifying data isolation

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
    """Run the session management sample."""
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
            name="MultiTenantAgent",
            instructions="You are a helpful assistant that remembers prior turns.",
            context_providers=[history_provider],
            default_options={"store": False},
        ) as agent,
    ):
        # 1. Tenant "alice" starts a conversation about travel.
        print("=== Tenant: Alice — Travel conversation ===\n")

        alice_session = agent.create_session(session_id="tenant-alice-session-1")

        response = await agent.run("Hi! I'm planning a trip to Italy. I love Renaissance art.", session=alice_session)
        print("Alice:     I'm planning a trip to Italy. I love Renaissance art.")
        print(f"Assistant: {response.text}\n")

        response = await agent.run("Which museums should I visit in Florence?", session=alice_session)
        print("Alice:     Which museums should I visit in Florence?")
        print(f"Assistant: {response.text}\n")

        # 2. Tenant "bob" starts a separate conversation about cooking.
        print("=== Tenant: Bob — Cooking conversation ===\n")

        bob_session = agent.create_session(session_id="tenant-bob-session-1")

        response = await agent.run("Hey! I'm learning to cook Thai food. I just made pad thai.", session=bob_session)
        print("Bob:       I'm learning to cook Thai food. I just made pad thai.")
        print(f"Assistant: {response.text}\n")

        response = await agent.run("What Thai dish should I try next?", session=bob_session)
        print("Bob:       What Thai dish should I try next?")
        print(f"Assistant: {response.text}\n")

        # 3. List all sessions stored in Cosmos DB.
        print("=== Listing all sessions ===\n")

        sessions = await history_provider.list_sessions()
        print(f"Found {len(sessions)} session(s):")
        for sid in sessions:
            print(f"  - {sid}")

        # 4. Resume Alice's session — verify she gets her travel context back.
        print("\n=== Resuming Alice's session ===\n")

        alice_resumed = agent.create_session(session_id="tenant-alice-session-1")

        response = await agent.run("What were we discussing?", session=alice_resumed)
        print("Alice:     What were we discussing?")
        print(f"Assistant: {response.text}\n")

        # 5. Resume Bob's session — verify he gets his cooking context back.
        print("=== Resuming Bob's session ===\n")

        bob_resumed = agent.create_session(session_id="tenant-bob-session-1")

        response = await agent.run("What was the last dish I mentioned?", session=bob_resumed)
        print("Bob:       What was the last dish I mentioned?")
        print(f"Assistant: {response.text}\n")

        # 6. Show per-session message counts.
        print("=== Per-session message counts ===\n")

        alice_messages = await history_provider.get_messages("tenant-alice-session-1")
        bob_messages = await history_provider.get_messages("tenant-bob-session-1")
        print(f"Alice's session: {len(alice_messages)} messages")
        print(f"Bob's session:   {len(bob_messages)} messages")

        # 7. Clean up: clear both sessions.
        print("\n=== Cleaning up ===\n")

        await history_provider.clear("tenant-alice-session-1")
        await history_provider.clear("tenant-bob-session-1")
        print("Cleared Alice's and Bob's sessions.")


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:
=== Tenant: Alice — Travel conversation ===

Alice:     I'm planning a trip to Italy. I love Renaissance art.
Assistant: Italy is a dream for Renaissance art lovers! Florence, Rome, and Venice ...

Alice:     Which museums should I visit in Florence?
Assistant: In Florence, the Uffizi Gallery is a must — it has Botticelli's Birth of Venus ...

=== Tenant: Bob — Cooking conversation ===

Bob:       I'm learning to cook Thai food. I just made pad thai.
Assistant: Pad thai is a great start! How did it turn out?

Bob:       What Thai dish should I try next?
Assistant: I'd suggest trying green curry or tom yum soup — both are classic Thai dishes ...

=== Listing all sessions ===

Found 2 session(s):
  - tenant-alice-session-1
  - tenant-bob-session-1

=== Resuming Alice's session ===

Alice:     What were we discussing?
Assistant: We were discussing your trip to Italy and your love for Renaissance art ...

=== Resuming Bob's session ===

Bob:       What was the last dish I mentioned?
Assistant: You mentioned pad thai — it was the dish you just made!

=== Per-session message counts ===

Alice's session: 6 messages
Bob's session:   6 messages

=== Cleaning up ===

Cleared Alice's and Bob's sessions.
"""
