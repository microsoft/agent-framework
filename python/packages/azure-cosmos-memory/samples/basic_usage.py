# Copyright (c) Microsoft. All rights reserved.
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "agent-framework-azure-cosmos-memory",
#     "agent-framework-foundry",
#     "python-dotenv",
# ]
# ///

"""Basic usage of CosmosMemoryContextProvider with an agent.

Attach the provider to an ``Agent`` and it transparently searches long-term memory
before each run (injecting relevant memories) and stores the conversation turns
afterwards for background fact/summary extraction.

Set these environment variables (or put them in a ``.env`` file) before running:
    COSMOS_ENDPOINT     Azure Cosmos DB account endpoint
    FOUNDRY_ENDPOINT    Azure AI Foundry project endpoint (chat + embeddings)

Optional:
    COSMOS_DATABASE     Database name (default: ai_memory)
    CHAT_MODEL          Chat deployment (default: gpt-4o-mini)
    EMBEDDING_MODEL     Embedding deployment (default: text-embedding-3-large)

Run:
    python samples/basic_usage.py
"""

import asyncio
import os

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import DefaultAzureCredential
from dotenv import load_dotenv

from agent_framework_azure_cosmos_memory import CosmosMemoryContextProvider


def _build_agent(provider: CosmosMemoryContextProvider, credential: DefaultAzureCredential) -> Agent:
    """Build an agent that uses the memory provider and the same Foundry endpoint for chat."""
    return Agent(
        client=FoundryChatClient(
            project_endpoint=os.environ["FOUNDRY_ENDPOINT"],
            model=os.getenv("CHAT_MODEL", "gpt-4o-mini"),
            credential=credential,
        ),
        name="Memory Assistant",
        instructions="You are a helpful assistant with long-term memory about the user.",
        context_providers=[provider],
    )


async def user_scoped_memory() -> None:
    """Memory scoped to a stable user id, so it persists across sessions and threads."""
    credential = DefaultAzureCredential()
    provider = CosmosMemoryContextProvider(
        cosmos_endpoint=os.environ["COSMOS_ENDPOINT"],
        foundry_endpoint=os.environ["FOUNDRY_ENDPOINT"],
        embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-large"),
        chat_model=os.getenv("CHAT_MODEL", "gpt-4o-mini"),
        credential=credential,
    )
    agent = _build_agent(provider, credential)

    async with provider:
        session = agent.create_session()
        # Provider state is scoped by source id; set a stable user id there so memory
        # persists across sessions rather than being limited to this one.
        session.state.setdefault(provider.source_id, {})["user_id"] = "alice"
        first = await agent.run("I love hiking and I'm allergic to peanuts.", session=session)
        print("Assistant:", first.text)

        # A brand-new session for the same user still recalls the earlier facts.
        new_session = agent.create_session()
        new_session.state.setdefault(provider.source_id, {})["user_id"] = "alice"
        recall = await agent.run("What do you remember about me?", session=new_session)
        print("Assistant:", recall.text)

        # Let background extraction finish and persist before the client closes.
        await provider.flush()


async def session_scoped_memory() -> None:
    """Without a user id, memory is scoped to the session id (single-session recall)."""
    credential = DefaultAzureCredential()
    provider = CosmosMemoryContextProvider(
        cosmos_endpoint=os.environ["COSMOS_ENDPOINT"],
        foundry_endpoint=os.environ["FOUNDRY_ENDPOINT"],
        embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-large"),
        chat_model=os.getenv("CHAT_MODEL", "gpt-4o-mini"),
        credential=credential,
    )
    agent = _build_agent(provider, credential)

    async with provider:
        # No user_id in provider state -> memory is scoped to this session's id.
        session = agent.create_session()
        await agent.run("Remember that my project uses FastAPI and PostgreSQL.", session=session)
        followup = await agent.run("Which web framework am I using?", session=session)
        print("Assistant:", followup.text)
        await provider.flush()


async def main() -> None:
    load_dotenv()
    print("=== User-scoped memory ===")
    await user_scoped_memory()
    print("\n=== Session-scoped memory ===")
    await session_scoped_memory()


if __name__ == "__main__":
    asyncio.run(main())
