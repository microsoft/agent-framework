# Copyright (c) Microsoft. All rights reserved.
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "agent-framework-azure-cosmos-memory",
#     "agent-framework-foundry",
#     "python-dotenv",
# ]
# ///

"""Interactive chat demonstrating CosmosMemoryContextProvider with an agent.

Talk to an agent that remembers you across conversations. Facts and preferences you
mention are extracted in the background and recalled in later threads and sessions.

Set these environment variables (or put them in a ``.env`` file) before running:
    COSMOS_ENDPOINT     Azure Cosmos DB account endpoint
    FOUNDRY_ENDPOINT    Azure AI Foundry project endpoint (chat + embeddings)

Optional:
    COSMOS_DATABASE     Database name (default: ai_memory)
    CHAT_MODEL          Chat deployment (default: gpt-4o-mini)
    EMBEDDING_MODEL     Embedding deployment (default: text-embedding-3-large)

Run:
    python samples/interactive_chat.py
"""

import asyncio
import os
import sys

from agent_framework import Agent, AgentSession
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import DefaultAzureCredential
from dotenv import load_dotenv

from agent_framework_azure_cosmos_memory import CosmosMemoryContextProvider


def create_agent_with_memory() -> tuple[Agent, CosmosMemoryContextProvider]:
    """Create an agent wired to Cosmos DB long-term memory."""
    cosmos_endpoint = os.environ.get("COSMOS_ENDPOINT")
    foundry_endpoint = os.environ.get("FOUNDRY_ENDPOINT")
    if not cosmos_endpoint or not foundry_endpoint:
        print("ERROR: set COSMOS_ENDPOINT and FOUNDRY_ENDPOINT (see this file's docstring).")
        sys.exit(1)

    # A single Foundry endpoint powers both the memory pipeline (embeddings + extraction)
    # and the chat agent below. Auth is via DefaultAzureCredential (az login / managed identity).
    credential = DefaultAzureCredential()
    provider = CosmosMemoryContextProvider(
        cosmos_endpoint=cosmos_endpoint,
        cosmos_database=os.getenv("COSMOS_DATABASE", "ai_memory"),
        foundry_endpoint=foundry_endpoint,
        credential=credential,
        top_k=5,
        min_confidence=0.7,
        memory_types=["fact", "procedural", "episodic"],
        context_prompt="## What I Remember About You\nI'll use these memories to personalize my responses:",
    )
    agent = Agent(
        client=FoundryChatClient(
            project_endpoint=foundry_endpoint,
            model=os.getenv("CHAT_MODEL", "gpt-4o-mini"),
            credential=credential,
        ),
        name="Memory Assistant",
        instructions=(
            "You are a helpful assistant with long-term memory. "
            "When you remember facts about the user, mention them naturally. "
            "If you don't remember something, say so instead of guessing."
        ),
        context_providers=[provider],
    )
    return agent, provider


def _new_thread(agent: Agent, provider: CosmosMemoryContextProvider, user_id: str) -> AgentSession:
    """Start a fresh session (a new thread) scoped to the given user id.

    A new session gets a new session id, which the provider uses as the thread id. Setting a
    stable ``user_id`` in the provider-scoped state keeps memory available across threads.
    """
    session = agent.create_session()
    session.state.setdefault(provider.source_id, {})["user_id"] = user_id
    return session


async def chat_loop(agent: Agent, provider: CosmosMemoryContextProvider, user_id: str) -> None:
    """Run the interactive chat loop."""
    print("\n" + "=" * 70)
    print("  Interactive Chat with Cosmos DB Memory")
    print("=" * 70)
    print(f"\nUser ID: {user_id}")
    print("\nCommands:  /new (new thread)   /user (switch user)   /quit")
    print("Tip: tell the assistant your preferences, then /new and see if it remembers.\n")

    session = _new_thread(agent, provider, user_id)
    print(f"Started thread: {session.session_id}\n")

    while True:
        user_input = input("You: ").strip()
        if not user_input:
            continue
        if user_input == "/quit":
            print("\nGoodbye!")
            break
        if user_input == "/new":
            session = _new_thread(agent, provider, user_id)
            print(f"\n[New thread: {session.session_id} - earlier memories still available]\n")
            continue
        if user_input == "/user":
            new_user_id = input("Enter new user ID: ").strip()
            if new_user_id:
                user_id = new_user_id
                session = _new_thread(agent, provider, user_id)
                print(f"\n[Switched to user {user_id}; new thread {session.session_id}]\n")
            continue

        response = await agent.run(user_input, session=session)
        print(f"\nAssistant: {response.text}\n")


async def main() -> None:
    """Entry point."""
    load_dotenv()
    agent, provider = create_agent_with_memory()
    async with provider:
        try:
            await chat_loop(agent, provider, user_id="demo-user-123")
        finally:
            # Let in-flight background extraction finish and persist before the client closes.
            print("Finalizing memory extraction...")
            await provider.flush()


if __name__ == "__main__":
    asyncio.run(main())
