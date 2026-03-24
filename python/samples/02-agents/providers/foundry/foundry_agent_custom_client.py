# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import Agent
from agent_framework.foundry import FoundryAgent, RawFoundryAgentChatClient
from azure.identity import AzureCliCredential

"""
Foundry Agent — Custom client configuration

This sample demonstrates three ways to customize the FoundryAgent client layer:

1. Default: FoundryAgent creates a RawFoundryAgentChatClient (full middleware) internally
2. client_type: Pass RawFoundryAgentChatClient for no client middleware
3. Composition: Use Agent(client=RawFoundryAgentChatClient(...)) directly

Environment variables:
    FOUNDRY_PROJECT_ENDPOINT — Azure AI Foundry project endpoint
    FOUNDRY_AGENT_NAME       — Name of the agent in Foundry
    FOUNDRY_AGENT_VERSION    — Version of the agent
"""


async def main() -> None:
    # Option 1: Default — full middleware on both agent and client
    agent = FoundryAgent(
        project_endpoint="https://your-project.services.ai.azure.com",
        agent_name="my-agent",
        agent_version="1.0",
        credential=AzureCliCredential(),
    )
    result = await agent.run("Hello from the default setup!")
    print(f"Default: {result}\n")

    # Option 2: Raw client — no client-level middleware (agent middleware still active)
    agent_raw_client = FoundryAgent(
        project_endpoint="https://your-project.services.ai.azure.com",
        agent_name="my-agent",
        agent_version="1.0",
        credential=AzureCliCredential(),
        client_type=RawFoundryAgentChatClient,
    )
    result = await agent_raw_client.run("Hello from raw client!")
    print(f"Raw client: {result}\n")

    # Option 3: Composition — use Agent(client=...) directly
    # this will not run the checks that the `FoundryAgent` does on things like tools.
    client = RawFoundryAgentChatClient(
        project_endpoint="https://your-project.services.ai.azure.com",
        agent_name="my-agent",
        agent_version="1.0",
        credential=AzureCliCredential(),
    )
    agent_composed = Agent(client=client)
    result = await agent_composed.run("Hello from composed setup!")
    print(f"Composed: {result}")


if __name__ == "__main__":
    asyncio.run(main())
