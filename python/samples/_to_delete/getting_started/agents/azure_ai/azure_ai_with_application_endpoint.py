# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework import ChatAgent
from agent_framework.azure import AzureAIClient
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import AzureCliCredential

"""
Azure AI Agent with Application Endpoint Example

This sample demonstrates working with pre-existing Azure AI Agents by providing
application endpoint instead of project endpoint.
"""


async def main() -> None:
    # Create the client
    async with (
        AzureCliCredential() as credential,
        # Endpoint here should be application endpoint with format:
        # /api/projects/<project-name>/applications/<application-name>/protocols
        AIProjectClient(endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"], credential=credential) as project_client,
        ChatAgent(
            chat_client=AzureAIClient(
                project_client=project_client,
            ),
        ) as agent,
    ):
        query = "How are you?"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result}\n")


if __name__ == "__main__":
    asyncio.run(main())
