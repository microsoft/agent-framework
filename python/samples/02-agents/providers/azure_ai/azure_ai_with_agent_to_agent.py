# Copyright (c) Microsoft. All rights reserved.
import asyncio
import os

from agent_framework.azure import AzureAIProjectAgentProvider
from azure.identity.aio import AzureCliCredential

"""
Azure AI Agent with Agent-to-Agent (A2A) Example

This sample demonstrates usage of AzureAIProjectAgentProvider with Agent-to-Agent (A2A) capabilities
to enable communication with other agents using the A2A protocol.

Prerequisites:
1. Set AZURE_AI_PROJECT_ENDPOINT and AZURE_AI_MODEL_DEPLOYMENT_NAME environment variables.
2. Ensure you have an A2A connection configured in your Azure AI project
   and set A2A_PROJECT_CONNECTION_ID environment variable.
3. (Optional) A2A_ENDPOINT - If the connection is missing target (e.g., "Custom keys" type),
   set the A2A endpoint URL directly.
"""


async def main() -> None:
    # Configure A2A tool with connection ID
    a2a_tool = {
        "type": "a2a_preview",
        "project_connection_id": os.environ["A2A_PROJECT_CONNECTION_ID"],
    }

    # If the connection is missing a target, we need to set the A2A endpoint URL
    if os.environ.get("A2A_ENDPOINT"):
        a2a_tool["base_url"] = os.environ["A2A_ENDPOINT"]

    async with (
        AzureCliCredential() as credential,
        AzureAIProjectAgentProvider(credential=credential) as provider,
    ):
        agent = await provider.create_agent(
            name="MyA2AAgent",
            instructions="""You are a helpful assistant that can communicate with other agents.
            Use the A2A tool when you need to interact with other agents to complete tasks
            or gather information from specialized agents.""",
            tools=a2a_tool,
        )

        query = "What can the secondary agent do?"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Result: {result}\n")


if __name__ == "__main__":
    asyncio.run(main())
