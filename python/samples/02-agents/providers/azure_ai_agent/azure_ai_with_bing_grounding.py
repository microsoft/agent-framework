# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework.azure import AzureAIAgentClient, AzureAIAgentsProvider
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
The following sample demonstrates how to create an Azure AI agent that
uses Bing Grounding search to find real-time information from the web.

Prerequisites:
1. A connected Grounding with Bing Search resource in your Azure AI project
2. Set BING_CONNECTION_ID environment variable
   Example: BING_CONNECTION_ID="your-bing-connection-id"

To set up Bing Grounding:
1. Go to Azure AI Foundry portal (https://ai.azure.com)
2. Navigate to your project's "Connected resources" section
3. Add a new connection for "Grounding with Bing Search"
4. Copy either the connection name or ID and set the appropriate environment variable
"""


async def main() -> None:
    """Main function demonstrating Azure AI agent with Bing Grounding search."""
    # Use AzureAIAgentsProvider for agent creation and management
    async with (
        AzureCliCredential() as credential,
        AzureAIAgentsProvider(credential=credential) as provider,
    ):
        # Create a client to access hosted tool factory methods
        client = AzureAIAgentClient(credential=credential)
        # Create Bing Grounding search tool using instance method
        # The connection ID will be automatically picked up from environment variable
        bing_search_tool = client.get_web_search_tool()

        agent = await provider.create_agent(
            name="BingSearchAgent",
            instructions=(
                "You are a helpful assistant that can search the web for current information. "
                "Use the Bing search tool to find up-to-date information and provide accurate, "
                "well-sourced answers. Always cite your sources when possible."
            ),
            tools=[bing_search_tool],
        )

        # 3. Demonstrate agent capabilities with web search
        print("=== Azure AI Agent with Bing Grounding Search ===\n")

        user_input = "What is the most popular programming language?"
        print(f"User: {user_input}")
        response = await agent.run(user_input)
        print(f"Agent: {response.text}\n")


if __name__ == "__main__":
    asyncio.run(main())
