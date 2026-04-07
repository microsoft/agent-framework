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
for an agent, with writeback into the same Cosmos knowledge container after each run.

Key components:
- AzureOpenAIResponsesClient configured with an Azure AI project endpoint
- AzureCosmosContextProvider configured for Cosmos DB-backed retrieval
- Full-text retrieval over an existing Cosmos container of knowledge documents
- An agent session so writeback documents share the same `session_id`

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

When this provider is attached to an agent, the framework calls `before_run(...)`
using the provider's `default_search_mode`. This sample keeps that default as
full-text search for the normal agent flow. Advanced callers can still invoke
`before_run(..., search_mode=..., weights=..., top_k=..., scan_limit=..., partition_key=...)`
directly to override the provider defaults for a specific run.

This sample assumes the Cosmos account, database, container, and any required
full-text/vector/hybrid indexing policies are already provisioned and configured.
The provider does not create or manage Cosmos resources for you.
"""


def _require_setting(name: str) -> str:
    """Return a required environment variable or raise a readable error."""
    value = os.getenv(name)
    if value and value.strip():
        return value
    raise RuntimeError(
        f"Missing required environment variable '{name}'. See the sample docstring for the required configuration."
    )


async def main() -> None:
    """Run the Cosmos context provider sample with an Agent."""
    try:
        project_endpoint = _require_setting("AZURE_AI_PROJECT_ENDPOINT")
        deployment_name = _require_setting("AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME")
        cosmos_endpoint = _require_setting("AZURE_COSMOS_ENDPOINT")
        cosmos_database_name = _require_setting("AZURE_COSMOS_DATABASE_NAME")
        cosmos_container_name = _require_setting("AZURE_COSMOS_CONTAINER_NAME")
    except RuntimeError as exc:
        print(exc)
        return

    cosmos_key = os.getenv("AZURE_COSMOS_KEY")
    cosmos_partition_key = os.getenv("AZURE_COSMOS_CONTEXT_PARTITION_KEY")

    # 1. Create an Azure credential and Responses client using project endpoint auth.
    async with AzureCliCredential() as credential:
        responses_client = AzureOpenAIResponsesClient(
            project_endpoint=project_endpoint,
            deployment_name=deployment_name,
            credential=credential,
        )

        # 2. Create a Cosmos context provider that retrieves from an existing
        #    knowledge container. Keep the default search mode explicit so it is
        #    easy to see what the attached agent will use for normal runs.
        async with (
            AzureCosmosContextProvider(
                endpoint=cosmos_endpoint,
                database_name=cosmos_database_name,
                container_name=cosmos_container_name,
                credential=cosmos_key or credential,
                default_search_mode=CosmosContextSearchMode.FULL_TEXT,
                partition_key=cosmos_partition_key,
                content_field_names=("content", "text"),
                title_field_name="title",
                url_field_name="url",
                metadata_field_name="metadata",
            ) as context_provider,
            responses_client.as_agent(
                name="CosmosContextAgent",
                instructions="Use Cosmos retrieval context when it is relevant to answer the user.",
                context_providers=[context_provider],
                default_options={"store": False},
            ) as agent,
        ):
            # 3. Create a session so writeback documents share a stable session_id.
            session = agent.create_session()

            # 4. Ask a question that should retrieve supporting context from Cosmos.
            response = await agent.run(
                "Explain hybrid search in Cosmos DB and when I should use it.",
                session=session,
            )
            print(f"Assistant: {response.text}")
            print(f"Default search mode: {context_provider.default_search_mode.value}")
            print(f"Container: {context_provider.container_name}")
            print(f"Session id: {session.session_id}")


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:
Assistant: Hybrid search combines lexical and vector-style relevance so you can match
both exact terms and semantic meaning.
Default search mode: full_text
Container: <AZURE_COSMOS_CONTAINER_NAME>
Session id: <generated-session-id>
"""
