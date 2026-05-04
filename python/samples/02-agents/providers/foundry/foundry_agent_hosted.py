# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework.foundry import FoundryAgent
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

load_dotenv()

"""
Foundry Agent — Connect to a HostedAgent (no version needed)

HostedAgents in Azure AI Foundry are pre-deployed agents that don't require
a version number. You only need the agent name to connect.

Environment variables:
    FOUNDRY_PROJECT_ENDPOINT — Azure AI Foundry project endpoint
    FOUNDRY_AGENT_NAME       — Name of the hosted agent
"""


async def main() -> None:
    # HostedAgents don't need agent_version
    agent = FoundryAgent(
        project_endpoint=os.getenv("FOUNDRY_PROJECT_ENDPOINT"),
        agent_name=os.getenv("FOUNDRY_AGENT_NAME"),
        credential=AzureCliCredential(),
    )

    result = await agent.run("Summarize the latest news about AI.")
    print(f"Agent: {result}")


if __name__ == "__main__":
    asyncio.run(main())
