# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework import Agent
from agent_framework.azure import AzureAISearchContextProvider
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity.aio import DefaultAzureCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


async def main():
    credential = DefaultAzureCredential()

    # Connect to a pre-provisioned Azure AI Search index. The index is expected to
    # exist and contain documents with the schema described in README.md
    # (id / content / sourceName / sourceLink). The context provider runs a search
    # against this index before each model invocation and injects the matching
    # documents into the model context.
    search_provider = AzureAISearchContextProvider(
        source_id="azure_search_rag",
        endpoint=os.environ["AZURE_SEARCH_ENDPOINT"],
        index_name=os.environ["AZURE_SEARCH_INDEX_NAME"],
        credential=credential,
        mode="semantic",
        top_k=3,
    )

    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=credential,
    )

    async with (
        search_provider,
        Agent(
            client=client,
            instructions=(
                "You are a helpful support specialist for Contoso Outdoors. "
                "Answer questions using the provided context and cite the source "
                "document when available."
            ),
            context_providers=[search_provider],
            # History will be managed by the hosting infrastructure, thus there
            # is no need to store history by the service. Learn more at:
            # https://developers.openai.com/api/reference/resources/responses/methods/create
            default_options={"store": False},
        ) as agent,
    ):
        server = ResponsesHostServer(agent)
        await server.run_async()


if __name__ == "__main__":
    asyncio.run(main())
