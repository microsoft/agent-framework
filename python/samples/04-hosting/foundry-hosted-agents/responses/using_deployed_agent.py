# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping
from typing import Any, cast

from agent_framework import AgentSession
from agent_framework.foundry import FoundryAgent
from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.models import VersionRefIndicator
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

After you deploy one of the agents in this directory, you can run this sample
to connect to it and have a conversation.

Note: The `allow_preview=True` flag is required to connect to the new hosted
agents, as this is a preview feature in Foundry.

"""


async def create_hosted_agent_session(
    *,
    agent: FoundryAgent,
    project_client: AIProjectClient,
    agent_name: str,
    agent_version: str | None,
    isolation_key: str,
) -> AgentSession:
    """Create a hosted-agent service session and wrap it in an AgentSession."""
    create_session_kwargs: dict[str, Any] = {
        "agent_name": agent_name,
        "isolation_key": isolation_key,
    }
    resolved_agent_version = agent_version
    if resolved_agent_version is None:
        agent_details = await cast(Any, project_client.beta.agents).get(  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
            agent_name=agent_name
        )
        versions = getattr(agent_details, "versions", None)
        if not isinstance(versions, Mapping):
            raise ValueError("Hosted agent details did not include a versions mapping.")
        latest_version = getattr(cast(Any, versions.get("latest")), "version", None)
        if not isinstance(latest_version, str) or not latest_version:
            raise ValueError("Hosted agent details did not include a latest version string.")
        resolved_agent_version = latest_version

    create_session_kwargs["version_indicator"] = VersionRefIndicator(agent_version=resolved_agent_version)
    service_session = await project_client.beta.agents.create_session(**create_session_kwargs)
    agent_session_id = getattr(service_session, "agent_session_id", None)
    if not isinstance(agent_session_id, str) or not agent_session_id:
        raise ValueError("Hosted agent session creation did not return a non-empty agent_session_id.")

    return agent.get_session(agent_session_id)


async def main() -> None:
    credential = AzureCliCredential()
    project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    agent_name = os.environ["FOUNDRY_AGENT_NAME"]
    agent_version = os.getenv("FOUNDRY_AGENT_VERSION")
    isolation_key = "my-isolation-key"

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
        session = await create_hosted_agent_session(
            agent=agent,
            project_client=project_client,
            agent_name=agent_name,
            agent_version=agent_version,
            isolation_key=isolation_key,
        )

        try:
            # 1. Send the first turn.
            query = "Hi!"
            print(f"User: {query}")
            print("Agent: ", end="", flush=True)
            async for chunk in agent.run(query, session=session, stream=True):
                if chunk.text:
                    print(chunk.text, end="", flush=True)

            # 2. Continue the conversation with the same deployed agent session.
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
        finally:
            if session.service_session_id is not None:
                await project_client.beta.agents.delete_session(
                    agent_name=agent_name,
                    session_id=session.service_session_id,
                    isolation_key=isolation_key,
                )


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
