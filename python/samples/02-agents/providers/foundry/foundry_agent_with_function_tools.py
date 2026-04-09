# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from typing import Annotated

from agent_framework.foundry import FoundryAgent
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

load_dotenv()
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


def get_weather(
    location: Annotated[str, "The city to get weather for."],
) -> str:
    """Get the current weather for a location."""
    return f"The weather in {location} is sunny, 22°C."


async def main() -> None:
    agent = FoundryAgent(
        project_endpoint=os.getenv("FOUNDRY_PROJECT_ENDPOINT"),
        agent_name=os.getenv("FOUNDRY_AGENT_NAME"),
        agent_version=os.getenv("FOUNDRY_AGENT_VERSION"),
        credential=AzureCliCredential(),
        tools=get_weather,
    )

    result = await agent.run("What's the weather in Paris?")
    print(f"Agent: {result}")


if __name__ == "__main__":
    asyncio.run(main())
