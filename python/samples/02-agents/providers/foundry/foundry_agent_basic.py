# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework.foundry import FoundryAgent
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
"""
Foundry Agent — Connect to a pre-configured agent in Microsoft Foundry

This sample shows the simplest way to connect to an existing PromptAgent
in Azure AI Foundry and run it. The agent's instructions, model, and hosted
tools are all configured on the service — you just connect and run.

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

    result = await agent.run("What is the capital of France?")
    print(f"Agent: {result}")

    # Streaming
    print("Agent (streaming): ", end="", flush=True)
    async for chunk in agent.run("Tell me a fun fact.", stream=True):
        if chunk.text:
            print(chunk.text, end="", flush=True)
    print()


if __name__ == "__main__":
    asyncio.run(main())
