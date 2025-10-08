# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import ChatAgent, HostedFileSearchTool
from agent_framework.azure import AzureAIAgentClient
from azure.identity.aio import AzureCliCredential

"""
Azure AI Agent with Azure AI Search Example

This sample demonstrates how to create an Azure AI agent that uses Azure AI Search
to search through indexed hotel data and answer user questions about hotels.

Prerequisites:
1. Set AZURE_AI_PROJECT_ENDPOINT and AZURE_AI_MODEL_DEPLOYMENT_NAME environment variables
2. Ensure you have an Azure AI Search connection configured in your Azure AI project
3. The search index "hotels-sample-index" should exist in your Azure AI Search service
   (you can create this using the Azure portal with sample hotel data)

Environment variables:
- AZURE_AI_PROJECT_ENDPOINT: Your Azure AI project endpoint
- AZURE_AI_MODEL_DEPLOYMENT_NAME: The name of your model deployment
"""

# Test queries to verify Azure AI Search is working with the hotels-sample-index
USER_INPUTS = [
    "Search the hotel database for Stay-Kay City Hotel and give me detailed information.",
]


async def main() -> None:
    """Main function demonstrating Azure AI agent with Azure AI Search capabilities."""

    # 1. Create Azure AI Search tool using HostedFileSearchTool
    # The tool will automatically use the default Azure AI Search connection from your project
    azure_ai_search_tool = HostedFileSearchTool(
        additional_properties={
            "index_name": "hotels-sample-index",  # Name of your search index
            "query_type": "simple",  # Use simple search
            "top_k": 10,  # Get more comprehensive results
        },
    )

    # 2. Use AzureAIAgentClient as async context manager for automatic cleanup
    async with (
        AzureAIAgentClient(async_credential=AzureCliCredential()) as client,
        ChatAgent(
            chat_client=client,
            name="HotelSearchAgent",
            instructions=("You are a helpful travel assistant that searches hotel information."),
            tools=azure_ai_search_tool,
        ) as agent,
    ):
        print("=== Azure AI Agent with Azure AI Search ===")
        print("This agent can search through hotel data to help you find accommodations.\n")

        # 3. Simulate conversation with the agent
        for user_input in USER_INPUTS:
            print(f"User: {user_input}")
            print("Agent: ", end="", flush=True)

            # Stream the response for better user experience
            async for chunk in agent.run_stream(user_input):
                if chunk.text:
                    print(chunk.text, end="", flush=True)
            print("\n" + "=" * 50 + "\n")

        print("Hotel search conversation completed!")


if __name__ == "__main__":
    asyncio.run(main())
