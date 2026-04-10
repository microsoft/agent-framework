# Copyright (c) Microsoft. All rights reserved.

import asyncio
import logging
import os
from datetime import datetime, timezone

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient, FoundryMemoryProvider
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.ai.agentserver.responses import InMemoryResponseProvider
from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.models import (
    MemoryStoreDefaultDefinition,
    MemoryStoreDefaultOptions,
)
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logging.basicConfig(level=logging.INFO)


async def _create_memory_store(project_client: AIProjectClient) -> FoundryMemoryProvider:
    memory_store_name = f"hosted_agent_memory_{datetime.now(timezone.utc).strftime('%Y%m%d')}"
    options = MemoryStoreDefaultOptions(
        chat_summary_enabled=True,
        user_profile_enabled=True,
        user_profile_details=(
            "Avoid irrelevant or sensitive data, such as age, financials, precise location, and credentials"
        ),
    )
    memory_store_definition = MemoryStoreDefaultDefinition(
        chat_model=os.environ["FOUNDRY_MODEL"],
        embedding_model=os.environ["AZURE_OPENAI_EMBEDDING_MODEL"],
        options=options,
    )
    memory_store = await project_client.beta.memory_stores.create(
        name=memory_store_name,
        description="Memory store for Agent Framework with FoundryMemoryProvider",
        definition=memory_store_definition,
    )

    return FoundryMemoryProvider(
        project_client=project_client,
        memory_store_name=memory_store.name,
        # Scope memories to a specific user, if not set, the session_id
        # will be used as scope, which means memories are only shared within the same session
        scope="demo",
        # Do not wait to update memories after each interaction (for demo purposes)
        # In production, consider setting a delay to batch updates and reduce costs
        update_delay=0,
    )


async def _delete_memory_store(project_client: AIProjectClient, memory_store_name: str):
    await project_client.beta.memory_stores.delete(name=memory_store_name)


async def main():
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=AzureCliCredential(),
    )

    # Create the memory store
    memory_provider = await _create_memory_store(client.project_client)

    agent = Agent(
        client=client,
        instructions="You are a friendly assistant. Keep your answers brief.",
        context_providers=[memory_provider],
        # History will be managed by the hosting infrastructure, thus there
        # is no need to store history by the service. Learn more at:
        # https://developers.openai.com/api/reference/resources/responses/methods/create
        default_options={"store": False},
    )

    server = ResponsesHostServer(agent, provider=InMemoryResponseProvider())

    try:
        await server.run_async()
    finally:
        await _delete_memory_store(client.project_client, memory_provider.memory_store_name)


if __name__ == "__main__":
    asyncio.run(main())
