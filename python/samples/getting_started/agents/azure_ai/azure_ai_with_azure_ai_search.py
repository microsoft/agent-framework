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

NOTE: To ensure consistent search tool usage:
- Include explicit instructions for the agent to use the search tool
- Mention the search requirement in your queries
- Use `tool_choice="required"` to force tool usage (uncomment in agent config)
"""


async def main() -> None:
    """Main function demonstrating Azure AI agent with Azure AI Search capabilities."""

    # 1. Create Azure AI Search tool using HostedFileSearchTool
    azure_ai_search_tool = HostedFileSearchTool(
        additional_properties={
            "index_name": "hotels-sample-index",  # Name of your search index
            "query_type": "simple",  # Use simple search
            "top_k": 3,
        },
    )

    # 2. Use AzureAIAgentClient as async context manager for automatic cleanup
    async with (
        AzureAIAgentClient(async_credential=AzureCliCredential()) as client,
        ChatAgent(
            chat_client=client,
            name="HotelSearchAgent",
            instructions=(
                "You are a helpful agent that only gives hotel information "
                "based on the search index using the search tool."
            ),
            tools=azure_ai_search_tool,
            # tool_choice="required",
        ) as agent,
    ):
        print("=== Azure AI Agent with Azure AI Search ===")
        print("This agent can search through hotel data to help you find accommodations.\n")

        # 3. Simulate conversation with the agent
        user_input = "Use the search tool to find detailed information about Stay-Kay City Hotel."
        print(f"User: {user_input}")
        print("Agent: ", end="", flush=True)

        # Stream the response and collect citations
        citations = []
        async for chunk in agent.run_stream(user_input):
            if chunk.text:
                print(chunk.text, end="", flush=True)

            # Collect citations from Azure AI Search responses
            if hasattr(chunk, "contents") and chunk.contents:
                for content in chunk.contents:
                    if hasattr(content, "annotations") and content.annotations:
                        citations.extend(content.annotations)  # type: ignore

        print()

        # Display citation details from Azure AI Search
        if citations:
            print("\nCitations from Azure AI Search:")
            for i, citation in enumerate(citations, 1):  # type: ignore
                print(f"  [{i}] Document: {citation.title}")  # type: ignore
                print(f"      Reference: {citation.url}")  # type: ignore

        print("\n" + "=" * 50 + "\n")

        print("Hotel search conversation completed!")


if __name__ == "__main__":
    asyncio.run(main())
