# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework import ChatAgent, CitationAnnotation
from agent_framework.azure import AzureAIAgentClient
from azure.ai.agents.aio import AgentsClient
from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.models import ConnectionType
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
- Use `tool_choice="required"` to force tool usage

More info on `query type` can be found here:
https://learn.microsoft.com/en-us/python/api/azure-ai-agents/azure.ai.agents.models.aisearchindexresource?view=azure-python-preview
"""


async def main() -> None:
    """Main function demonstrating Azure AI agent with raw Azure AI Search tool."""
    print("=== Azure AI Agent with Raw Azure AI Search Tool ===")

    # Create the client and manually create an agent with Azure AI Search tool
    async with (
        AzureCliCredential() as credential,
        AIProjectClient(endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"], credential=credential) as project_client,
        AgentsClient(endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"], credential=credential) as agents_client,
    ):
        ai_search_conn_id = ""
        async for connection in project_client.connections.list():
            if connection.type == ConnectionType.AZURE_AI_SEARCH:
                ai_search_conn_id = connection.id
                break

        # 1. Create Azure AI agent with the search tool
        azure_ai_agent = await agents_client.create_agent(
            model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            name="HotelSearchAgent",
            instructions=(
                "You are a helpful agent that searches hotel information using Azure AI Search. "
                "Always use the search tool and index to find hotel data and provide accurate information."
            ),
            tools=[{"type": "azure_ai_search"}],
            tool_resources={
                "azure_ai_search": {
                    "indexes": [
                        {
                            "index_connection_id": ai_search_conn_id,
                            "index_name": "hotels-sample-index",
                            "query_type": "vector",
                        }
                    ]
                }
            },
        )

        # 2. Create chat client with the existing agent
        chat_client = AzureAIAgentClient(agents_client=agents_client, agent_id=azure_ai_agent.id)

        try:
            async with ChatAgent(
                chat_client=chat_client,
                # Additional instructions for this specific conversation
                instructions=("You are a helpful agent that uses the search tool and index to find hotel information."),
            ) as agent:
                print("This agent uses raw Azure AI Search tool to search hotel data.\n")

                # 3. Simulate conversation with the agent
                user_input = (
                    "Use Azure AI search knowledge tool to find detailed information about a winter hotel."
                    " Use the search tool and index."  # You can modify prompt to force tool usage
                )
                print(f"User: {user_input}")
                print("Agent: ", end="", flush=True)

                # Stream the response and collect citations
                citations: list[CitationAnnotation] = []
                async for chunk in agent.run_stream(user_input):
                    if chunk.text:
                        print(chunk.text, end="", flush=True)

                    # Collect citations from Azure AI Search responses
                    for content in getattr(chunk, "contents", []):
                        annotations = getattr(content, "annotations", [])
                        if annotations:
                            citations.extend(annotations)

                print()

                # Display collected citations
                if citations:
                    print("\n\nCitations:")
                    for i, citation in enumerate(citations, 1):
                        print(f"[{i}] Reference: {citation.url}")

                print("\n" + "=" * 50 + "\n")
                print("Hotel search conversation completed!")

        finally:
            # Clean up the agent manually
            await agents_client.delete_agent(azure_ai_agent.id)


if __name__ == "__main__":
    asyncio.run(main())
