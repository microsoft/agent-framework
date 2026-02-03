# Copyright (c) Microsoft. All rights reserved.
import asyncio
import os

from agent_framework.azure import AzureAIProjectAgentProvider
from azure.identity.aio import AzureCliCredential

"""
Azure AI Agent with SharePoint Example

This sample demonstrates usage of AzureAIProjectAgentProvider with SharePoint
to search through SharePoint content and answer user questions about it.

Prerequisites:
1. Set AZURE_AI_PROJECT_ENDPOINT and AZURE_AI_MODEL_DEPLOYMENT_NAME environment variables.
2. Ensure you have a SharePoint connection configured in your Azure AI project
    and set SHAREPOINT_PROJECT_CONNECTION_ID environment variable.
"""


async def main() -> None:
    async with (
        AzureCliCredential() as credential,
        AzureAIProjectAgentProvider(credential=credential) as provider,
    ):
        agent = await provider.create_agent(
            name="MySharePointAgent",
            instructions="""You are a helpful agent that can use SharePoint tools to assist users.
            Use the available SharePoint tools to answer questions and perform tasks.""",
            tools={
                "type": "sharepoint_grounding_preview",
                "sharepoint_grounding_preview": {
                    "project_connections": [
                        {
                            "project_connection_id": os.environ["SHAREPOINT_PROJECT_CONNECTION_ID"],
                        }
                    ]
                },
            },
        )

        query = "What is Contoso whistleblower policy?"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Result: {result}\n")


if __name__ == "__main__":
    asyncio.run(main())
