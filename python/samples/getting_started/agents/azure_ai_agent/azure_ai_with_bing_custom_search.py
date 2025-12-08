# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import ChatAgent, HostedWebSearchTool
from agent_framework.azure import AzureAIAgentClient
from azure.identity.aio import AzureCliCredential

"""
The following sample demonstrates how to create an Azure AI agent that
uses Bing Custom Search to find real-time information from the web.

More information on Bing Custom Search and difference from Bing Grounding can be found here:
https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/tools/bing-custom-search

Prerequisites:
1. A connected Grounding with Bing Custom Search resource in your Azure AI project
2. Set BING_CUSTOM_CONNECTION_ID environment variable
   Example: BING_CUSTOM_CONNECTION_ID="your-bing-custom-connection-id"
3. Set BING_CUSTOM_INSTANCE_NAME environment variable
   Example: BING_CUSTOM_INSTANCE_NAME="your-bing-custom-instance-name"

To set up Bing Custom Search:
1. Go to Azure AI Foundry portal (https://ai.azure.com)
2. Navigate to your project's "Connected resources" section
3. Add a new connection for "Grounding with Bing Custom Search"
4. Copy the connection ID and instance name and set the appropriate environment variables
"""


async def main() -> None:
    """Main function demonstrating Azure AI agent with Bing Custom Search."""
    # 1. Create Bing Custom Search tool using HostedWebSearchTool
    # The connection ID and instance name will be automatically picked up from environment variables
    bing_search_tool = HostedWebSearchTool(
        name="Bing Custom Search",
        description="Search the web for current information using Bing Custom Search",
    )

    # 2. Use AzureAIAgentClient as async context manager for automatic cleanup
    async with (
        AzureAIAgentClient(credential=AzureCliCredential()) as client,
        ChatAgent(
            chat_client=client,
            name="BingSearchAgent",
            instructions=(
                "You are a helpful agent that can use Bing Custom Search tools to assist users. "
                "Use the available Bing Custom Search tools to answer questions and perform tasks."
            ),
            tools=bing_search_tool,
        ) as agent,
    ):
        # 3. Demonstrate agent capabilities with bing custom search
        print("=== Azure AI Agent with Bing Custom Search ===\n")

        user_input = "Tell me more about foundry agent service"
        print(f"User: {user_input}")
        response = await agent.run(user_input)
        print(f"Agent: {response.text}\n")


if __name__ == "__main__":
    asyncio.run(main())
