# Copyright (c) Microsoft. All rights reserved.
import asyncio
import os

from agent_framework.azure import AzureAIClient
from azure.identity.aio import AzureCliCredential

"""
Azure AI Agent with Agent-to-Agent (A2A) Example

This sample demonstrates usage of AzureAIClient with Agent-to-Agent (A2A) capabilities
to enable communication with other agents using the A2A protocol.

Prerequisites:
1. Set AZURE_AI_PROJECT_ENDPOINT and AZURE_AI_MODEL_DEPLOYMENT_NAME environment variables.
2. Ensure you have an A2A connection configured in your Azure AI project
    and set A2A_PROJECT_CONNECTION_ID environment variable.
"""


async def main() -> None:
    async with (
        AzureCliCredential() as credential,
        AzureAIClient(credential=credential).create_agent(
            name="MyA2AAgent",
            instructions="""You are a helpful assistant that can communicate with other agents.
            Use the A2A tool when you need to interact with other agents to complete tasks
            or gather information from specialized agents.""",
            tools={
                "type": "a2a_preview",
                "project_connection_id": os.environ["A2A_PROJECT_CONNECTION_ID"],
            },
        ) as agent,
    ):
        query = "What can the secondary agent do?"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Result: {result}\n")


if __name__ == "__main__":
    asyncio.run(main())
