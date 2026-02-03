# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import Annotation, HostedWebSearchTool
from agent_framework.azure import AzureAIAgentsProvider
from azure.identity.aio import AzureCliCredential

"""
This sample demonstrates how to create an Azure AI agent that uses Bing Grounding
search to find real-time information from the web with comprehensive citation support.
It shows how to extract and display citations (title, URL, and snippet) from Bing
Grounding responses, enabling users to verify sources and explore referenced content.

Prerequisites:
1. A connected Grounding with Bing Search resource in your Azure AI project
2. Set BING_CONNECTION_ID environment variable
   Example: BING_CONNECTION_ID="your-bing-connection-id"

To set up Bing Grounding:
1. Go to Azure AI Foundry portal (https://ai.azure.com)
2. Navigate to your project's "Connected resources" section
3. Add a new connection for "Grounding with Bing Search"
4. Copy the connection ID and set the BING_CONNECTION_ID environment variable
"""


async def main() -> None:
    """Main function demonstrating Azure AI agent with Bing Grounding search."""
    # 1. Create Bing Grounding search tool using HostedWebSearchTool
    # The connection ID will be automatically picked up from environment variable
    bing_search_tool = HostedWebSearchTool(
        name="Bing Grounding Search",
        description="Search the web for current information using Bing",
    )

    # 2. Use AzureAIAgentsProvider for agent creation and management
    async with (
        AzureCliCredential() as credential,
        AzureAIAgentsProvider(credential=credential) as provider,
    ):
        agent = await provider.create_agent(
            name="BingSearchAgent",
            instructions=(
                "You are a helpful assistant that can search the web for current information. "
                "Use the Bing search tool to find up-to-date information and provide accurate, "
                "well-sourced answers. Always cite your sources when possible."
            ),
            tools=bing_search_tool,
        )

        # 3. Demonstrate agent capabilities with web search
        print("=== Azure AI Agent with Bing Grounding Search ===\n")

        user_input = "What is the most popular programming language?"
        print(f"User: {user_input}")
        print("Agent: ", end="", flush=True)

        # Stream the response and collect citations
        citations: list[Annotation] = []
        async for chunk in agent.run_stream(user_input):
            if chunk.text:
                print(chunk.text, end="", flush=True)

            # Collect citations from Bing Grounding responses
            for content in getattr(chunk, "contents", []):
                annotations = getattr(content, "annotations", [])
                if annotations:
                    citations.extend(annotations)

        print()

        # Display collected citations
        if citations:
            print("\n\nCitations:")
            for i, citation in enumerate(citations, 1):
                print(f"[{i}] {citation['title']}: {citation.get('url')}")
                if "snippet" in citation:
                    print(f"    Snippet: {citation.get('snippet')}")
        else:
            print("\nNo citations found in the response.")

        print()


if __name__ == "__main__":
    asyncio.run(main())
