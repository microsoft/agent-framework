# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import os

from agent_framework import AgentSession
from agent_framework.foundry import FoundryAgent
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv

load_dotenv()

"""
This sample demonstrates how to connect to the deployed basic Foundry agent with
`FoundryAgent`.

The sample uses environment variables for configuration, which can be set in a .env file or in the environment directly:
Environment variables:
    FOUNDRY_PROJECT_ENDPOINT: Microsoft Foundry project endpoint.
    FOUNDRY_AGENT_NAME: Hosted agent name.
    FOUNDRY_AGENT_VERSION: Hosted agent version. Optional, defaults to latest if not specified.

After you deploy one of the agents in this directory, you can run this sample
to connect to it and have a conversation.

Note: The `allow_preview=True` flag is required to connect to the new hosted
agents, as this is a preview feature in Foundry.

"""


async def main() -> None:
    credential = AzureCliCredential()
    project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    agent_name = os.environ["FOUNDRY_AGENT_NAME"]
    agent_version = os.getenv("FOUNDRY_AGENT_VERSION")

    project_client = AIProjectClient(
        endpoint=project_endpoint,
        credential=credential,
        allow_preview=True,
    )
    async with (
        project_client,
        FoundryAgent(
            project_client=project_client,
            agent_name=agent_name,
            agent_version=agent_version,
            allow_preview=True,
        ) as agent,
    ):
        # Create a new session to manage the response chain (from a Responses API)
        # and to persist the Foundry hosted-agent session ID across multiple calls to the agent.
        session = AgentSession()

        # 1. Send the first turn. Foundry creates the hosted-agent session.
        query = "Hi!"
        print(f"User: {query}")
        print("Agent: ", end="", flush=True)
        async for chunk in agent.run(query, session=session, stream=True):
            if chunk.text:
                print(chunk.text, end="", flush=True)

        # 2. Continue the conversation with the service-created session.
        query = "Your name is Javis. What can you do?"
        print(f"\nUser: {query}")
        print("Agent: ", end="", flush=True)
        async for chunk in agent.run(query, session=session, stream=True):
            if chunk.text:
                print(chunk.text, end="", flush=True)

        # 3. Ask a follow-up question in the same session.
        query = "What is your name?"
        print(f"\nUser: {query}")
        print("Agent: ", end="", flush=True)
        async for chunk in agent.run(query, session=session, stream=True):
            if chunk.text:
                print(chunk.text, end="", flush=True)


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:
User: Hi!
Agent: Hello! How can I help you today?
User: Your name is Javis. What can you do?
Agent: I can answer questions and help with tasks using the instructions configured on the deployed agent.
User: What is your name?
Agent: My name is Javis.
"""
