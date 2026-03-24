# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Annotated

from agent_framework import tool
from agent_framework.foundry import FoundryAgent
from azure.identity import AzureCliCredential
from pydantic import Field

"""
Foundry Agent with Local Function Tools

This sample shows how to connect to a Foundry agent and provide local function
tools. The Foundry agent must already have these tools defined in its configuration
(as declaration-only tools). The local implementations are matched by name.

Only FunctionTool objects are accepted — hosted tools (code interpreter, file search,
web search, etc.) must be configured on the agent definition in the service.

Environment variables:
    FOUNDRY_PROJECT_ENDPOINT — Azure AI Foundry project endpoint
    FOUNDRY_AGENT_NAME       — Name of the agent in Foundry
    FOUNDRY_AGENT_VERSION    — Version of the agent
"""


@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, Field(description="The city to get weather for.")],
) -> str:
    """Get the current weather for a location."""
    return f"The weather in {location} is sunny, 22°C."


async def main() -> None:
    agent = FoundryAgent(
        project_endpoint="https://your-project.services.ai.azure.com",
        agent_name="my-weather-agent",
        agent_version="1.0",
        credential=AzureCliCredential(),
        tools=[get_weather],
    )

    result = await agent.run("What's the weather in Paris?")
    print(f"Agent: {result}")


if __name__ == "__main__":
    asyncio.run(main())
