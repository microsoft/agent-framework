# Copyright (c) Microsoft. All rights reserved.
import asyncio
import os
from typing import Any

from agent_framework._types import AgentRunResponse, CitationAnnotation, TextContent
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


def extract_citations_from_response(response: AgentRunResponse) -> list[dict[str, Any]]:
    """Extract citation information from an AgentRunResponse."""
    citations: list[dict[str, Any]] = []

    if hasattr(response, "messages") and response.messages:
        for message in response.messages:
            if hasattr(message, "contents") and message.contents:
                for content in message.contents:
                    if isinstance(content, TextContent) and hasattr(content, "annotations") and content.annotations:
                        for annotation in content.annotations:
                            if isinstance(annotation, CitationAnnotation):
                                citation_info = {
                                    "url": annotation.url,
                                    "title": getattr(annotation, "title", None),
                                    "file_id": getattr(annotation, "file_id", None),
                                }

                                # Extract text position information
                                if hasattr(annotation, "annotated_regions") and annotation.annotated_regions:
                                    citation_info["positions"] = [
                                        {
                                            "start_index": region.start_index,
                                            "end_index": region.end_index,
                                        }
                                        for region in annotation.annotated_regions
                                    ]

                                citations.append(citation_info)

    return citations


async def main() -> None:
    async with (
        AzureCliCredential() as credential,
        AzureAIClient(credential=credential).create_agent(
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
                            "query_type": "vector",
                        }
                    ]
                },
            },
        ) as agent,
    ):
        query = (
            "Use Azure AI search knowledge tool to find detailed information about a winter hotel."
            " Use the search tool and index."
        )
        print(f"User: {query}")

        # Get the response
        response = await agent.run(query)
        print(f"Agent: {response}\n")

        # Extract citation data
        citations = extract_citations_from_response(response)

        print("=== CITATION INFORMATION ===")
        if citations:
            for i, citation in enumerate(citations, 1):
                print(f"Citation {i}:")
                print(f"  URL: {citation['url']}")
        else:
            print("No citations found in the response.")


if __name__ == "__main__":
    asyncio.run(main())
