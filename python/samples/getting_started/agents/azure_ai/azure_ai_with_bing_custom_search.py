# Copyright (c) Microsoft. All rights reserved.
import asyncio
import os

from agent_framework.azure import AzureAIClient
from azure.identity.aio import AzureCliCredential

"""
Azure AI Agent with Bing Custom Search Example

This sample demonstrates usage of AzureAIClient with Bing Custom Search
to search custom search instances and provide responses with relevant results.

Prerequisites:
1. Set AZURE_AI_PROJECT_ENDPOINT and AZURE_AI_MODEL_DEPLOYMENT_NAME environment variables.
2. Ensure you have a Bing Custom Search connection configured in your Azure AI project
   and set BING_CUSTOM_SEARCH_PROJECT_CONNECTION_ID and BING_CUSTOM_SEARCH_INSTANCE_NAME environment variables.
"""


async def main() -> None:
    async with (
        AzureCliCredential() as credential,
        AzureAIClient(credential=credential).create_agent(
            name="MyCustomSearchAgent",
            instructions="""You are a helpful agent that can use Bing Custom Search tools to assist users.
            Use the available Bing Custom Search tools to answer questions and perform tasks.""",
            tools={
                "type": "bing_custom_search_preview",
                "bing_custom_search_preview": {
                    "search_configurations": [
                        {
                            "project_connection_id": os.environ["BING_CUSTOM_SEARCH_PROJECT_CONNECTION_ID"],
                            "instance_name": os.environ["BING_CUSTOM_SEARCH_INSTANCE_NAME"],
                        }
                    ]
                },
            },
        ) as agent,
    ):
        query = "Tell me more about foundry agent service"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Result: {result}\n")


if __name__ == "__main__":
    asyncio.run(main())
