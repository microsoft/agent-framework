# Copyright (c) Microsoft. All rights reserved.
import asyncio
import os

from agent_framework.azure import AzureAIClient
from azure.identity.aio import AzureCliCredential

"""
Azure AI Agent with Azure AI Search Example

This sample demonstrates usage of AzureAIClient with Azure AI Search
to search through indexed data and answer user questions about it.

Prerequisites:
1. Set AZURE_AI_PROJECT_ENDPOINT and AZURE_AI_MODEL_DEPLOYMENT_NAME environment variables.
2. Ensure you have an Azure AI Search connection configured in your Azure AI project
    and set AI_SEARCH_PROJECT_CONNECTION_ID and AI_SEARCH_INDEX_NAME environment variable.
"""


async def main() -> None:
    async with (
        AzureCliCredential() as credential,
        AzureAIClient(async_credential=credential).create_agent(
            name="MySearchAgent",
            instructions="""You are a helpful assistant. You must always provide citations for
            answers using the tool and render them as: `[message_idx:search_idx†source]`.""",
            tools={
                "type": "azure_ai_search",
                "azure_ai_search": {
                    "indexes": [
                        {
                            "project_connection_id": os.environ["AI_SEARCH_PROJECT_CONNECTION_ID"],
                            "index_name": os.environ["AI_SEARCH_INDEX_NAME"],
                            # For query_type=vector, ensure your index has a field with vectorized data.
                            "query_type": "simple",
                        }
                    ]
                },
            },
        ) as agent,
    ):
        query = "Tell me about insurance options"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Result: {result}\n")


if __name__ == "__main__":
    asyncio.run(main())
