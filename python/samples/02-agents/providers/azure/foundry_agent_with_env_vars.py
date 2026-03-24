# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework.foundry import FoundryAgent
from azure.identity import AzureCliCredential

"""
Foundry Agent with Environment Variables

This sample shows the recommended pattern for advanced samples that use
environment variables for configuration.

Environment variables:
    FOUNDRY_PROJECT_ENDPOINT — Azure AI Foundry project endpoint
    FOUNDRY_AGENT_NAME       — Name of the agent in Foundry
    FOUNDRY_AGENT_VERSION    — Version of the agent (optional, for PromptAgents)
"""


async def main() -> None:
    agent = FoundryAgent(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        agent_name=os.environ["FOUNDRY_AGENT_NAME"],
        agent_version=os.environ.get("FOUNDRY_AGENT_VERSION"),
        credential=AzureCliCredential(),
    )

    session = agent.create_session()

    result = await agent.run("Hello! My name is Alice.", session=session)
    print(f"Agent: {result}\n")

    result = await agent.run("What's my name?", session=session)
    print(f"Agent: {result}")


if __name__ == "__main__":
    asyncio.run(main())
