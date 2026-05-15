# Copyright (c) Microsoft. All rights reserved.

"""Foundry Memory hosted agent sample.

This agent uses :class:`FoundryMemoryProvider` to give an otherwise stateless
hosted agent persistent, semantic memory backed by an Azure AI Foundry
Memory Store. The store itself is provisioned once via
``provision_memory_store.py`` and its name is passed in through the
``MEMORY_STORE_NAME`` environment variable.

Unlike the standalone ``azure_ai_foundry_memory.py`` sample, here we construct
the :class:`FoundryChatClient` first and then reuse its underlying
``AIProjectClient`` for the memory provider, so both share a single client
instance and authentication context.
"""

import asyncio
import os

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient, FoundryMemoryProvider
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity.aio import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()


async def main() -> None:
    # The chat client owns the AIProjectClient. ``allow_preview=True`` is required
    # so the same client can call the preview ``beta.memory_stores`` API used by
    # FoundryMemoryProvider.
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=DefaultAzureCredential(),
        allow_preview=True,
    )

    # Reuse the project_client that FoundryChatClient just created, instead of
    # constructing a second one for the memory provider.
    memory_provider = FoundryMemoryProvider(
        project_client=client.project_client,
        memory_store_name=os.environ["MEMORY_STORE_NAME"],
        # Scope memories by user id, so each user that interacts with the agent
        # has their own isolated memories in the store (assuming those users are
        # granted access). `{{userId}}` is a special placeholder that the hosting
        # infrastructure will replace with the actual user id at runtime.
        scope="{{$userId}}",
    )

    agent = Agent(
        client=client,
        instructions=(
            "You are a helpful assistant that remembers facts the user has shared "
            "across conversations. Relevant memories from previous interactions are "
            "automatically provided to you in the system context. Use them when "
            "answering, and acknowledge when you are relying on remembered facts."
        ),
        context_providers=[memory_provider],
        # History will be managed by the hosting infrastructure, thus there
        # is no need to store history by the service. Learn more at:
        # https://developers.openai.com/api/reference/resources/responses/methods/create
        default_options={"store": False},
    )
    server = ResponsesHostServer(agent)
    await server.run_async()


if __name__ == "__main__":
    asyncio.run(main())
