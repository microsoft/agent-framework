# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import os

from agent_framework.foundry import FoundryAgent
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

load_dotenv()

"""
This sample demonstrates how to connect to the deployed basic Foundry agent with
`FoundryAgent`.

The sample uses environment variables for configuration, which can be set in a .env file or in the environment directly:
Environment variables:
    FOUNDRY_PROJECT_ENDPOINT: Azure AI Foundry project endpoint.
    FOUNDRY_AGENT_NAME: Hosted agent name.
    FOUNDRY_AGENT_VERSION: Hosted agent version. Optional, defaults to latest if not specified.

After you deployed one of the agents in this directory using the deploy script, you can run this sample to connect to it and have a conversation.

Note: The `allow_preview=True` flag is required to connect to the new hosted agents, as this is a preview feature in Foundry.

"""


async def main() -> None:
    # 1. Connect to the deployed basic Foundry agent.
    async with FoundryAgent(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        agent_name=os.environ["FOUNDRY_AGENT_NAME"],
        agent_version=os.getenv("FOUNDRY_AGENT_VERSION"),
        credential=AzureCliCredential(),
        allow_preview=True,
    ) as agent:
        # 2. Create a AgentSession in the Foundry Hosted Agent service.
        # The remote Foundry hosted-agent session
        # is created and the ID is stored in the AgentSession object for subsequent turns.
        session = await agent.create_service_session(isolation_key="my-isolation-key")

        # 3. Send the first turn.
        query = "Hi!"
        print(f"User: {query}")
        print("Agent: ", end="", flush=True)
        async for chunk in agent.run(query, session=session, stream=True):
            if chunk.text:
                print(chunk.text, end="", flush=True)

        # 4. Continue the conversation with the same deployed agent session.
        query = "Your name is Javis. What can you do?"
        print(f"\nUser: {query}")
        print("Agent: ", end="", flush=True)
        async for chunk in agent.run(query, session=session, stream=True):
            if chunk.text:
                print(chunk.text, end="", flush=True)

        # 5. Ask a follow-up question in the same session.
        query = "What is your name?"
        print(f"\nUser: {query}")
        print("Agent: ", end="", flush=True)
        async for chunk in agent.run(query, session=session, stream=True):
            if chunk.text:
                print(chunk.text, end="", flush=True)

        await agent.delete_service_session(session, isolation_key="my-isolation-key")


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
