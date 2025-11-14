# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import HostedWebSearchTool
from agent_framework.azure import AzureAIClient
from azure.identity.aio import AzureCliCredential

"""
Azure AI Agent With Web Search

This sample demonstrates basic usage of AzureAIClient to create an agent
that can perform web searches using the HostedWebSearchTool.

Pre-requisites:
- Make sure to set up the AZURE_AI_PROJECT_ENDPOINT and AZURE_AI_MODEL_DEPLOYMENT_NAME
  environment variables before running this sample.
"""


async def main() -> None:
    # Since no Agent ID is provided, the agent will be automatically created.
    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    async with (
        AzureCliCredential() as credential,
        AzureAIClient(async_credential=credential).create_agent(
            name="WebsearchAgent",
            instructions="You are a helpful assistant that can search the web",
            tools=[HostedWebSearchTool()],
        ) as agent,
    ):
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
