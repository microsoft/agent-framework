# Copyright (c) Microsoft. All rights reserved.
# ruff: noqa: T201

import asyncio
import os

from agent_framework import Agent, AgentSession
from agent_framework.foundry import FoundryChatClient
from agent_framework_azure_cosmos import CosmosHistoryProvider
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file.
load_dotenv()

"""
This sample demonstrates persisting and resuming conversations across application
restarts using CosmosHistoryProvider as the persistent backend.

Key components:
- Phase 1: Run a conversation and serialize the session with session.to_dict()
- Phase 2: Simulate an app restart — create new provider and agent instances,
  restore the session with AgentSession.from_dict(), and continue the conversation
- Cosmos DB reloads the full message history, so the agent remembers everything

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
    """Run the conversation persistence sample."""
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

    # ── Phase 1: Initial conversation ──

    print("=== Phase 1: Initial conversation ===\n")

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
            name="PersistentAgent",
            instructions="You are a helpful assistant that remembers prior turns.",
            context_providers=[history_provider],
            default_options={"store": False},
        ) as agent,
    ):
        session = agent.create_session()

        response1 = await agent.run("My name is Ada. I'm building a distributed database in Rust.", session=session)
        print("User:      My name is Ada. I'm building a distributed database in Rust.")
        print(f"Assistant: {response1.text}\n")

        response2 = await agent.run("The hardest part is the consensus algorithm.", session=session)
        print("User:      The hardest part is the consensus algorithm.")
        print(f"Assistant: {response2.text}\n")

        serialized_session = session.to_dict()
        print(f"Session serialized. Session ID: {session.session_id}")

    # ── Phase 2: Simulate app restart ──

    print("\n=== Phase 2: Resuming after 'restart' ===\n")

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
            name="PersistentAgent",
            instructions="You are a helpful assistant that remembers prior turns.",
            context_providers=[history_provider],
            default_options={"store": False},
        ) as agent,
    ):
        restored_session = AgentSession.from_dict(serialized_session)
        print(f"Session restored. Session ID: {restored_session.session_id}\n")

        response3 = await agent.run("What was I working on and what was the challenge?", session=restored_session)
        print("User:      What was I working on and what was the challenge?")
        print(f"Assistant: {response3.text}\n")

        messages = await history_provider.get_messages(restored_session.session_id)
        print(f"Messages stored in Cosmos DB: {len(messages)}")
        for i, msg in enumerate(messages, 1):
            print(f"  {i}. [{msg.role}] {msg.text[:80]}...")


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:
=== Phase 1: Initial conversation ===

User:      My name is Ada. I'm building a distributed database in Rust.
Assistant: That sounds like a great project, Ada! Rust is an excellent choice for ...

User:      The hardest part is the consensus algorithm.
Assistant: Consensus algorithms can be tricky! Are you looking at Raft, Paxos, or ...

Session serialized. Session ID: <session-uuid>

=== Phase 2: Resuming after 'restart' ===

Session restored. Session ID: <session-uuid>

User:      What was I working on and what was the challenge?
Assistant: You told me you're building a distributed database in Rust and that the hardest
part is the consensus algorithm.

Messages stored in Cosmos DB: 6
  1. [user] My name is Ada. I'm building a distributed database in Rust....
  2. [assistant] That sounds like a great project, Ada! Rust is an excellent ch...
  3. [user] The hardest part is the consensus algorithm....
  4. [assistant] Consensus algorithms can be tricky! Are you looking at Raft, Pa...
  5. [user] What was I working on and what was the challenge?...
  6. [assistant] You told me you're building a distributed database in Rust and ...
"""
