# Copyright (c) Microsoft. All rights reserved.
# ruff: noqa: T201

import asyncio
import os

from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv

from agent_framework_azure_cosmos import AzureCosmosContextProvider, CosmosContextSearchMode

# Load environment variables from .env file.
load_dotenv()

"""
This sample demonstrates AzureCosmosContextProvider as a context provider
for an agent, with default writeback into the same Cosmos knowledge container.

Key components:
- AzureOpenAIResponsesClient configured with an Azure AI project endpoint
- AzureCosmosContextProvider configured for Cosmos DB-backed retrieval
- Full-text retrieval over an existing Cosmos container of knowledge documents

Environment variables:
  AZURE_AI_PROJECT_ENDPOINT
  AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME
  AZURE_COSMOS_ENDPOINT
  AZURE_COSMOS_DATABASE_NAME
  AZURE_COSMOS_CONTAINER_NAME
Optional:
  AZURE_COSMOS_KEY
  AZURE_COSMOS_CONTEXT_PARTITION_KEY

Expected Cosmos document fields by default:
- content (or text)
Optional fields:
- title
- url
- metadata
"""


async def main() -> None:
    """Run the Cosmos context provider sample with an Agent."""
    project_endpoint = os.getenv("AZURE_AI_PROJECT_ENDPOINT")
    deployment_name = os.getenv("AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME")
    cosmos_endpoint = os.getenv("AZURE_COSMOS_ENDPOINT")
    cosmos_database_name = os.getenv("AZURE_COSMOS_DATABASE_NAME")
    cosmos_container_name = os.getenv("AZURE_COSMOS_CONTAINER_NAME")
    cosmos_key = os.getenv("AZURE_COSMOS_KEY")
    cosmos_partition_key = os.getenv("AZURE_COSMOS_CONTEXT_PARTITION_KEY")

    if (
        not project_endpoint
        or not deployment_name
        or not cosmos_endpoint
        or not cosmos_database_name
        or not cosmos_container_name
    ):
        print(
            "Please set AZURE_AI_PROJECT_ENDPOINT, AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME, "
            "AZURE_COSMOS_ENDPOINT, AZURE_COSMOS_DATABASE_NAME, and AZURE_COSMOS_CONTAINER_NAME."
        )
        return

    # 1. Create an Azure credential and Responses client using project endpoint auth.
    async with AzureCliCredential() as credential:
        client = AzureOpenAIResponsesClient(
            project_endpoint=project_endpoint,
            deployment_name=deployment_name,
            credential=credential,
        )

        # 2. Create a Cosmos context provider that retrieves from, and by default
        #    writes request/response messages back into, the same knowledge container.
        async with (
            AzureCosmosContextProvider(
                endpoint=cosmos_endpoint,
                database_name=cosmos_database_name,
                container_name=cosmos_container_name,
                credential=cosmos_key or credential,
                default_search_mode=CosmosContextSearchMode.FULL_TEXT,
                query_builder_mode="latest_user_with_context",
                partition_key=cosmos_partition_key,
                content_field_names=("content", "text"),
                title_field_name="title",
                url_field_name="url",
                metadata_field_name="metadata",
            ) as context_provider,
            client.as_agent(
                name="CosmosContextAgent",
                instructions="Use Cosmos retrieval context when it is relevant to answer the user.",
                context_providers=[context_provider],
                default_options={"store": False},
            ) as agent,
        ):
            # 3. Ask a question that should retrieve supporting context from Cosmos.
            response = await agent.run("Explain hybrid search in Cosmos DB and when I should use it.")
            print(f"Assistant: {response.text}")
            print(f"Default search mode: {context_provider.default_search_mode.value}")
            print(f"Container: {context_provider.container_name}")


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:
Assistant: Hybrid search combines lexical and vector-style relevance so you can match
both exact terms and semantic meaning.
Default search mode: full_text
Container: <AZURE_COSMOS_CONTAINER_NAME>
"""
