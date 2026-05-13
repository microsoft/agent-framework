# Copyright (c) Microsoft. All rights reserved.

"""Provision the Azure AI Foundry Memory Store used by this sample.

Creates the memory store named by ``FOUNDRY_MEMORY_STORE_NAME`` if it does not
already exist. The store is configured with the user-profile capability so the
agent can remember stable facts about a user across sessions; chat-summary is
disabled to keep the demo focused on durable preferences. Safe to re-run: if a
store with the same name already exists, the script leaves it alone.

Usage (from this directory, with the venv activated and ``az login`` done):

    python provision_memory_store.py

Required env vars (also read from a local ``.env`` file if present):

    FOUNDRY_PROJECT_ENDPOINT          e.g. https://<account>.services.ai.azure.com/api/projects/<project>
    AZURE_AI_MODEL_DEPLOYMENT_NAME    Chat model deployment used by the memory store
    AZURE_OPENAI_EMBEDDING_MODEL      Embedding model deployment used by the memory store
    FOUNDRY_MEMORY_STORE_NAME         Name of the memory store to create

Your identity needs ``Azure AI User`` on the Foundry project scope.
"""

import asyncio
import os

from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.models import (
    MemoryStoreDefaultDefinition,
    MemoryStoreDefaultOptions,
)
from azure.core.exceptions import ResourceNotFoundError
from azure.identity.aio import DefaultAzureCredential
from dotenv import load_dotenv


async def main() -> None:
    load_dotenv()

    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    memory_store_name = os.environ["FOUNDRY_MEMORY_STORE_NAME"]
    chat_model = os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"]
    embedding_model = os.environ["AZURE_OPENAI_EMBEDDING_MODEL"]

    async with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=endpoint, credential=credential, allow_preview=True) as project,
    ):
        try:
            existing = await project.beta.memory_stores.get(name=memory_store_name)
            print(f"Memory store '{existing.name}' already exists (id={existing.id}); leaving as-is.")
            return
        except ResourceNotFoundError:
            pass

        print(f"Creating memory store '{memory_store_name}'...")
        definition = MemoryStoreDefaultDefinition(
            chat_model=chat_model,
            embedding_model=embedding_model,
            options=MemoryStoreDefaultOptions(
                chat_summary_enabled=False,
                user_profile_enabled=True,
                user_profile_details=(
                    "Avoid irrelevant or sensitive data, such as age, financials, precise location, and credentials"
                ),
            ),
        )
        created = await project.beta.memory_stores.create(
            name=memory_store_name,
            description="Memory store for the Agent Framework foundry-hosted memory sample",
            definition=definition,
        )
        print(f"Created memory store '{created.name}' (id={created.id}).")


if __name__ == "__main__":
    asyncio.run(main())
