# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework.azure import AzureAIClient, AzureAIProjectAgentProvider
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
Azure AI Agent With Web Search

This sample demonstrates basic usage of AzureAIProjectAgentProvider to create an agent
that can perform web searches using get_web_search_tool().

Pre-requisites:
- Make sure to set up the AZURE_AI_PROJECT_ENDPOINT and AZURE_AI_MODEL_DEPLOYMENT_NAME
  environment variables before running this sample.
"""


async def main() -> None:
    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    async with (
        AzureCliCredential() as credential,
        AzureAIProjectAgentProvider(credential=credential) as provider,
    ):
        # Create a client to access hosted tool factory methods
        client = AzureAIClient(credential=credential)
        # Create web search tool using instance method
        web_search_tool = client.get_web_search_tool()

        agent = await provider.create_agent(
            name="WebsearchAgent",
            instructions="You are a helpful assistant that can search the web",
            tools=[web_search_tool],
        )

        query = "What's the weather today in Seattle?"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result}\n")

    """
    Sample output:
    User: What's the weather today in Seattle?
    Agent: Here is the updated weather forecast for Seattle: The current temperature is approximately 57°F,
           mostly cloudy conditions, with light winds and a chance of rain later tonight. Check out more details
           at the [National Weather Service](https://forecast.weather.gov/zipcity.php?inputstring=Seattle%2CWA).
    """


if __name__ == "__main__":
    asyncio.run(main())
