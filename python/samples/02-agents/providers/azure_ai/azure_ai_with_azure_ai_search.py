# Copyright (c) Microsoft. All rights reserved.
import asyncio
import os

from agent_framework import Annotation
from agent_framework.azure import AzureAIProjectAgentProvider
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
Azure AI Agent with Azure AI Search Example

This sample demonstrates usage of AzureAIProjectAgentProvider with Azure AI Search
to search through indexed data and answer user questions about it.

Citations from Azure AI Search are automatically enriched with document-specific
URLs (get_url) that can be used to retrieve the original documents.

Prerequisites:
1. Set AZURE_AI_PROJECT_ENDPOINT and AZURE_AI_MODEL_DEPLOYMENT_NAME environment variables.
2. Ensure you have an Azure AI Search connection configured in your Azure AI project
    and set AI_SEARCH_PROJECT_CONNECTION_ID and AI_SEARCH_INDEX_NAME environment variable.
"""


async def main() -> None:
    async with (
        AzureCliCredential() as credential,
        AzureAIProjectAgentProvider(credential=credential) as provider,
    ):
        agent = await provider.create_agent(
            name="MySearchAgent",
            instructions=(
                "You are a helpful agent that searches hotel information using Azure AI Search. "
                "Always use the search tool and index to find hotel data and provide accurate information."
            ),
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
        )

        query = (
            "Use Azure AI search knowledge tool to find detailed information about a winter hotel."
            " Use the search tool and index."  # You can modify prompt to force tool usage
        )
        print(f"User: {query}")

        # Non-streaming: get response with enriched citations
        result = await agent.run(query)
        print(f"Result: {result}\n")

        # Display citations with document-specific URLs
        if result.messages:
            citations: list[Annotation] = []
            for msg in result.messages:
                for content in msg.contents:
                    if hasattr(content, "annotations") and content.annotations:
                        citations.extend(content.annotations)

            if citations:
                print("Citations:")
                for i, citation in enumerate(citations, 1):
                    url = citation.get("url", "N/A")
                    # get_url contains the document-specific REST API URL from Azure AI Search
                    get_url = (citation.get("additional_properties") or {}).get("get_url")
                    print(f"  [{i}] {citation.get('title', 'N/A')}")
                    print(f"      URL: {url}")
                    if get_url:
                        print(f"      Document URL: {get_url}")

        # Streaming: collect citations from streamed response
        print("\n--- Streaming ---")
        print(f"User: {query}")
        print("Agent: ", end="", flush=True)
        streaming_citations: list[Annotation] = []
        async for chunk in agent.run(query, stream=True):
            if chunk.text:
                print(chunk.text, end="", flush=True)
            for content in getattr(chunk, "contents", []):
                annotations = getattr(content, "annotations", [])
                if annotations:
                    streaming_citations.extend(annotations)

        print()
        if streaming_citations:
            print("\nStreaming Citations:")
            for i, citation in enumerate(streaming_citations, 1):
                url = citation.get("url", "N/A")
                get_url = (citation.get("additional_properties") or {}).get("get_url")
                print(f"  [{i}] {citation.get('title', 'N/A')}")
                print(f"      URL: {url}")
                if get_url:
                    print(f"      Document URL: {get_url}")


if __name__ == "__main__":
    asyncio.run(main())
